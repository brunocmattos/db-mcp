from __future__ import annotations

import contextlib
import os
import socket
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TextIO

from pydantic import ValidationError

from .config import Settings
from .dialetos import Dialeto, obter_dialeto


@dataclass
class Resultado:
    ok: bool
    titulo: str
    detalhe: str = ""
    remediacao: str = ""  # como consertar, mostrado só quando falha


class PularChecagem(Exception):
    """Levantada quando um pré-requisito falhou (ex.: sem config, sem conexão)."""

    def __init__(self, motivo: str) -> None:
        self.motivo = motivo


class Contexto:
    """Estado compartilhado: uma checagem preenche, as seguintes reutilizam."""

    def __init__(
        self, env_file: str | None, yaml_file: str, dialeto_override: str | None = None
    ) -> None:
        self.env_file = env_file
        self.yaml_file = yaml_file
        self.dialeto_override = dialeto_override  # o --dialect da linha de comando
        self.settings: Settings | None = None  # preenchido por checar_config
        self.dialeto: Dialeto | None = None  # idem — resolvido a partir do settings
        # `Any`, não `psycopg.Connection`: a conexão vem do dialeto e o tipo muda por
        # driver. O doctor só a usa através do contrato (linhas_como_dict/probar_escrita).
        self.conn: Any = None  # preenchido por checar_auth


Checagem = Callable[[Contexto], Resultado]

# --- cor ANSI opcional (degrada) ---
RESET, NEGRITO = "\033[0m", "\033[1m"
VERDE, VERMELHO, AMARELO, CINZA = "\033[32m", "\033[31m", "\033[33m", "\033[90m"


def _habilitar_vt_windows() -> None:
    """Liga o processamento de ANSI no console do Windows (no-op nos demais SOs)."""
    # sys.platform (não os.name): é o que o mypy entende pra pular o bloco só-Windows quando
    # checa no Linux (o `ctypes.windll` não existe no typeshed de lá e viraria erro no strict).
    if sys.platform != "win32":
        return
    try:
        import ctypes

        k = ctypes.windll.kernel32
        k.SetConsoleMode(k.GetStdHandle(-11), 7)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass


def _decidir_cor(modo: str, stream: TextIO) -> bool:
    if modo == "never" or os.environ.get("NO_COLOR") is not None:
        return False
    if modo == "always" or os.environ.get("FORCE_COLOR") is not None:
        _habilitar_vt_windows()
        return True
    usar = hasattr(stream, "isatty") and stream.isatty()  # 'auto'
    if usar:
        _habilitar_vt_windows()
    return usar


def _suporta_emoji(stream: TextIO) -> bool:
    # Cobre TODOS os glifos nao-ASCII da saida (emojis + as decoracoes ↳ — ·).
    # Se o encoding do stream nao aguenta, degradamos tudo pra ASCII em vez de crashar.
    enc = getattr(stream, "encoding", None) or ""
    try:
        "✅❌⏭️↳—·".encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def _pinta(txt: str, cor: str, usar_cor: bool) -> str:
    return f"{cor}{txt}{RESET}" if usar_cor else txt


def _linha(r: Resultado, cor: bool, emoji: bool) -> None:
    if r.ok:
        marca, ico, c = "[OK]", "✅ ", VERDE
    else:
        marca, ico, c = "[X] ", "❌ ", VERMELHO
    prefixo = (ico if emoji else "") + _pinta(marca, c, cor)
    sep = "  —  " if emoji else "  -  "
    print(f"{prefixo} {r.titulo}" + (f"{sep}{r.detalhe}" if r.detalhe else ""))
    if not r.ok and r.remediacao:
        seta = "↳" if emoji else "->"
        print(_pinta(f"        {seta} {r.remediacao}", CINZA, cor))


def _linha_skip(titulo: str, motivo: str, cor: bool, emoji: bool) -> None:
    prefixo = ("⏭️ " if emoji else "") + _pinta("[--]", AMARELO, cor)
    sep = "  —  " if emoji else "  -  "
    print(f"{prefixo} {titulo}{sep}pulada ({motivo})")


CHECAGENS: list[Checagem] = []  # preenchido na Task 3


def rodar(checagens: list[Checagem], ctx: Contexto, cor: bool, emoji: bool) -> int:
    falhas = pulados = 0
    for fn in checagens:
        titulo_fn = (fn.__doc__ or fn.__name__).strip()
        try:
            r = fn(ctx)
        except PularChecagem as e:
            _linha_skip(titulo_fn, e.motivo, cor, emoji)
            pulados += 1
            continue
        except Exception as e:  # uma checagem nunca derruba o doctor
            r = Resultado(False, titulo_fn, f"erro inesperado: {e!r}")
        _linha(r, cor, emoji)
        if not r.ok:
            falhas += 1
    if ctx.conn is not None:
        ctx.conn.close()
    total = len(checagens)
    print()
    sep = " · " if emoji else " | "
    resumo = f"{total - falhas - pulados} ok{sep}{falhas} falha(s){sep}{pulados} pulada(s)"
    print(_pinta(resumo, VERDE if falhas == 0 else VERMELHO, cor))
    return 1 if falhas else 0


def executar_doctor(
    env_file: str | None,
    yaml_file: str,
    modo_cor: str = "auto",
    dialeto_override: str | None = None,
) -> int:
    # A saida nunca deve crashar por encoding: nem no console cp1252 do Windows,
    # nem quando o stdout e capturado por pipe (como o cliente MCP faz). UTF-8 quando
    # da, e errors="replace" como rede de seguranca.
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    ctx = Contexto(env_file, yaml_file, dialeto_override)
    cor = _decidir_cor(modo_cor, sys.stdout)
    emoji = _suporta_emoji(sys.stdout)
    print(_pinta("== db-mcp doctor ==", NEGRITO, cor))
    return rodar(CHECAGENS, ctx, cor, emoji)


def checar_config(ctx: Contexto) -> Resultado:
    "Config carregada e válida"
    try:
        ctx.settings = Settings.load(env_file=ctx.env_file, yaml_file=ctx.yaml_file)
    except ValidationError as e:
        campos = ", ".join(".".join(map(str, err["loc"])) for err in e.errors())
        return Resultado(
            False,
            "Config inválida",
            f"campos com problema: {campos}",
            "preencha .env / config.yaml (veja .env.example e config.example.yaml)",
        )
    except Exception as e:
        return Resultado(
            False,
            "Config não carregou",
            repr(e),
            "confira os caminhos passados em --env / --config",
        )
    s = ctx.settings
    if ctx.dialeto_override:  # --dialect da CLI vence a config, como no `run`
        s.dialeto = ctx.dialeto_override  # type: ignore[assignment]
    # O dialeto entra aqui porque tudo depois dele depende: porta padrão, conexão,
    # probe e SQL de identidade saem do contrato. Um dialeto aceito pela config mas
    # sem implementação (ou com o extra do driver faltando) morre com mensagem legível
    # em vez de estourar cru na próxima checagem.
    try:
        ctx.dialeto = obter_dialeto(s.dialeto)
    except Exception as e:
        return Resultado(
            False,
            "Dialeto indisponível",
            f"{s.dialeto!r}: {e}",
            f"dialeto sem implementação nesta versão, ou driver não instalado "
            f"(ex.: uv sync --extra {s.dialeto})",
        )
    return Resultado(
        True,
        "Config OK",
        f"{s.db_user}@{s.db_host}:{s.db_port or ctx.dialeto.porta_padrao}/{s.db_dbname}"
        f" · dialeto={ctx.dialeto.nome} · allowlist={s.allowlist}",
    )


def checar_tcp(ctx: Contexto) -> Resultado:
    "TCP alcança host:porta"
    if ctx.settings is None or ctx.dialeto is None:
        raise PularChecagem("config não carregou")
    s = ctx.settings
    porta = s.db_port or ctx.dialeto.porta_padrao
    t0 = time.perf_counter()
    try:
        with socket.create_connection((s.db_host, porta), timeout=5):
            pass
    except OSError as e:
        return Resultado(
            False,
            "TCP inacessível",
            f"{s.db_host}:{porta} — {e}",
            "verifique VPN, firewall e as regras de acesso do servidor (pg_hba.conf no Postgres)",
        )
    return Resultado(True, "TCP OK", f"conectou em {(time.perf_counter() - t0) * 1000:.0f} ms")


def checar_auth(ctx: Contexto) -> Resultado:
    "Autentica como o usuário read-only"
    if ctx.settings is None or ctx.dialeto is None:
        raise PularChecagem("config não carregou")
    d = ctx.dialeto
    try:
        ctx.conn = d.conectar_doctor(ctx.settings)
    except Exception as e:
        if not d.erro_do_banco(e):
            raise  # não é recusa do banco: sobe e vira "erro inesperado" no `rodar`
        return Resultado(
            False,
            "Falha de autenticação",
            str(e).strip(),
            "confira db_user/db_password/db_sslmode e a regra de acesso do servidor"
            " (linha do usuário no pg_hba.conf, no Postgres)",
        )
    with d.linhas_como_dict(ctx.conn) as cur:
        cur.execute(d.sql_identidade())
        linha = cur.fetchone()
    assert linha is not None  # SELECT de uma linha sempre retorna
    return Resultado(True, "Autenticou", f"current_user={linha['usuario']} · db={linha['banco']}")


def checar_somente_leitura(ctx: Contexto) -> Resultado:
    "Confirma que a conexão é somente-leitura"
    if ctx.conn is None or ctx.dialeto is None:
        raise PularChecagem("sem conexão")
    # QUAL escrita tentar, COMO revertê-la e QUAIS erros significam "write recusado"
    # mudam por banco (Postgres: 25006/42501 e transação revertível; MySQL: DDL com
    # commit implícito; SQL Server na Fase 2 nem tem transação READ ONLY) — por isso
    # a mecânica inteira mora no dialeto. Aqui só resta a leitura do veredito.
    d = ctx.dialeto
    try:
        d.probar_escrita(ctx.conn)
    except Exception as e:
        # Só o erro que o dialeto RECONHECE como recusa de escrita conta como prova.
        # Qualquer outro sobe e vira "erro inesperado" no `rodar` — nunca "somente-leitura
        # confirmado", que seria o falso positivo perigoso num cadeado que falha aberta.
        if not d.erro_readonly(e):
            raise
        # MEDIDO: pymssql (SQL Server) não expõe `.sqlstate` — sem o fallback pro
        # primeiro item de `.args` (onde o pymssql põe o número, ex. 262), a mensagem
        # perdia o único dado que identifica a recusa e sobrava só "OperationalError".
        # Postgres/MySQL têm `.sqlstate` de verdade, então nunca caem no fallback.
        codigo = getattr(e, "sqlstate", None)
        if not codigo:
            args: tuple[object, ...] = getattr(e, "args", ())
            codigo = args[0] if args else ""
        return Resultado(
            True,
            "Somente-leitura confirmado",
            f"write recusado: {codigo} {type(e).__name__}".strip(),
        )
    return Resultado(  # voltou sem erro = a escrita PASSOU
        False,
        "NÃO é somente-leitura",
        "o usuário do banco conseguiu executar a escrita de teste",
        "o usuário do MCP não pode ter DDL/DML: REVOKE ALL e conceda apenas SELECT",
    )


def checar_allowlist_existe(ctx: Contexto) -> Resultado:
    "Tabelas da allowlist existem"
    if ctx.conn is None or ctx.settings is None or ctx.dialeto is None:
        raise PularChecagem("sem conexão")
    d = ctx.dialeto
    alvos = [t for t in ctx.settings.allowlist if t != "*"]
    if not alvos:
        return Resultado(True, "Allowlist = todas (*)", "nada específico a verificar")

    pares = []
    for t in alvos:
        sch, _, tab = t.partition(".")
        pares.append((sch if tab else d.schema_padrao, tab or sch))

    # Laço Python, uma query por tabela: o `unnest(%s::text[])` de antes era Postgres puro
    # (array literal + cast). A allowlist tem punhado de itens, então N queries triviais no
    # doctor custam menos que um SQL que precise de uma forma por dialeto.
    faltando = []
    with d.linhas_como_dict(ctx.conn) as cur:
        for sch, tab in pares:
            cur.execute(
                "SELECT 1 AS existe FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = %s",
                (sch, tab),
            )
            if cur.fetchone() is None:
                faltando.append(f"{sch}.{tab}")
    if faltando:
        return Resultado(
            False,
            "Tabelas da allowlist ausentes",
            "não encontradas (ou sem privilégio p/ mcp_ro): " + ", ".join(faltando),
            "corrija os nomes (schema.tabela) na allowlist ou os GRANTs do mcp_ro",
        )
    return Resultado(True, "Allowlist confere", f"{len(alvos)} tabela(s) existem e são visíveis")


def checar_latencia(ctx: Contexto) -> Resultado:
    "Mede latência de uma query trivial (SELECT 1)"
    if ctx.conn is None or ctx.dialeto is None:
        raise PularChecagem("sem conexão")
    amostras = []
    with ctx.dialeto.linhas_como_dict(ctx.conn) as cur:
        for _ in range(5):
            t0 = time.perf_counter()
            # AS um: coluna sem nome. MEDIDO — o cursor as_dict do pymssql (SQL Server)
            # levanta ColumnsWithoutNamesError num "SELECT 1" cru; Postgres/MySQL não se
            # importam. Alias é SQL genérico, não conhecimento de dialeto — doctor.py
            # continua sem importar driver nenhum.
            cur.execute("SELECT 1 AS um")
            cur.fetchone()
            amostras.append((time.perf_counter() - t0) * 1000)
    amostras.sort()
    mediana = amostras[len(amostras) // 2]
    detalhe = f"mediana {mediana:.1f} ms (min {amostras[0]:.1f} · max {amostras[-1]:.1f})"
    if mediana > 2000:  # crítico -> falha
        return Resultado(
            False,
            "Latência SELECT 1",
            detalhe,
            "latência crítica: verifique a rota de rede/VPN até o banco",
        )
    if mediana > 250:  # aviso (ainda ok)
        return Resultado(True, "Latência SELECT 1", detalhe + "  (alta — atenção à VPN)")
    return Resultado(True, "Latência SELECT 1", detalhe)


# ordem importa: config -> tcp -> auth preenchem o Contexto; o resto reusa ctx.conn.
CHECAGENS = [
    checar_config,
    checar_tcp,
    checar_auth,
    checar_somente_leitura,
    checar_allowlist_existe,
    checar_latencia,
]
