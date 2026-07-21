import socket
from contextlib import contextmanager

import pytest

from db_mcp.doctor import (
    Contexto,
    PularChecagem,
    Resultado,
    checar_allowlist_existe,
    checar_auth,
    checar_config,
    checar_somente_leitura,
    checar_tcp,
    rodar,
)


def _ok(ctx):
    "checagem que sempre passa"
    return Resultado(True, "sempre ok", "detalhe")


def _falha(ctx):
    "checagem que sempre falha"
    return Resultado(False, "sempre falha", "detalhe", "conserte assim")


def _pula(ctx):
    "checagem pulada"
    raise PularChecagem("pre-requisito faltando")


def _explode(ctx):
    "checagem que estoura"
    raise RuntimeError("boom")


def test_rodar_tudo_ok_retorna_0(capsys):
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    assert rodar([_ok, _ok], ctx, cor=False, emoji=False) == 0


def test_rodar_com_falha_retorna_1(capsys):
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    assert rodar([_ok, _falha], ctx, cor=False, emoji=False) == 1


def test_rodar_pulada_nao_conta_como_falha(capsys):
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    assert rodar([_ok, _pula], ctx, cor=False, emoji=False) == 0


def test_rodar_excecao_vira_falha_sem_derrubar(capsys):
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    assert rodar([_explode], ctx, cor=False, emoji=False) == 1
    assert "boom" in capsys.readouterr().out


def _limpar_pg(monkeypatch):
    for k in ("DB_HOST", "DB_PORT", "DB_DBNAME", "DB_PASSWORD"):
        monkeypatch.delenv(k, raising=False)


def test_checar_config_ok(monkeypatch):
    _limpar_pg(monkeypatch)
    for k, v in {"DB_HOST": "h", "DB_DBNAME": "d", "DB_PASSWORD": "p"}.items():
        monkeypatch.setenv(k, v)
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    r = checar_config(ctx)
    assert r.ok
    assert ctx.settings is not None
    assert ctx.settings.db_host == "h"


def test_checar_config_falta_campo_obrigatorio(monkeypatch):
    _limpar_pg(monkeypatch)  # sem DB_HOST/DB_DBNAME/DB_PASSWORD -> ValidationError
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    r = checar_config(ctx)
    assert not r.ok
    assert ctx.settings is None


def test_checar_tcp_ok(monkeypatch):
    _limpar_pg(monkeypatch)
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    porta = srv.getsockname()[1]
    for k, v in {
        "DB_HOST": "127.0.0.1",
        "DB_PORT": str(porta),
        "DB_DBNAME": "d",
        "DB_PASSWORD": "p",
    }.items():
        monkeypatch.setenv(k, v)
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    checar_config(ctx)
    try:
        r = checar_tcp(ctx)
    finally:
        srv.close()
    assert r.ok


def test_checar_tcp_recusado(monkeypatch):
    _limpar_pg(monkeypatch)
    for k, v in {
        "DB_HOST": "127.0.0.1",
        "DB_PORT": "1",
        "DB_DBNAME": "d",
        "DB_PASSWORD": "p",
    }.items():
        monkeypatch.setenv(k, v)
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    checar_config(ctx)
    r = checar_tcp(ctx)
    assert not r.ok


def test_checar_tcp_pula_sem_config():
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")  # settings=None
    with pytest.raises(PularChecagem):
        checar_tcp(ctx)


def test_checar_config_dialeto_sem_implementacao(monkeypatch):
    # O Literal do config ACEITA "mysql", mas o _REGISTRO ainda não o resolve (Fase 1 T5).
    # Sem essa checagem o erro estouraria cru na próxima checagem, sem remediação.
    _limpar_pg(monkeypatch)
    for k, v in {"DB_HOST": "h", "DB_DBNAME": "d", "DB_PASSWORD": "p", "DIALETO": "mysql"}.items():
        monkeypatch.setenv(k, v)
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    r = checar_config(ctx)
    assert not r.ok
    assert r.titulo == "Dialeto indisponível"
    assert ctx.dialeto is None  # as checagens seguintes se PULAM, não estouram
    with pytest.raises(PularChecagem):
        checar_tcp(ctx)


# --- costura dialeto-aware do doctor (T3): dialeto e conexão falsos, sem banco ---


class _ErroReadonly(Exception):
    sqlstate = "25006"


class _CursorFake:
    """Cursor mínimo no formato que o doctor usa: execute(sql, params) + fetchone()."""

    def __init__(self, respostas):
        self._respostas = respostas  # callable(sql, params) -> linha | None
        self.chamadas = []
        self._ultima = None

    def execute(self, sql, params=None):
        self.chamadas.append((sql, params))
        self._ultima = self._respostas(sql, params)

    def fetchone(self):
        return self._ultima


class _DialetoFake:
    """Só o que o doctor toca. Prova que ele fala com o CONTRATO, não com o psycopg."""

    nome = "fake"
    # de propósito != "public": era esse literal que estava cravado no doctor, e com
    # o fake usando "public" o teste da allowlist passaria mesmo sem o refactor.
    schema_padrao = "sch_do_dialeto"
    porta_padrao = 1234

    def __init__(self, respostas=lambda sql, params: None, escrita_aceita=False, erro=None):
        self.cursor = _CursorFake(respostas)
        self.escrita_aceita = escrita_aceita
        self.erro = erro or _ErroReadonly("read-only")

    def erro_readonly(self, e):
        return isinstance(e, _ErroReadonly)

    @contextmanager
    def linhas_como_dict(self, conn):
        yield self.cursor

    def sql_identidade(self):
        return "SELECT identidade"

    def probar_escrita(self, conn):
        if self.escrita_aceita:
            return  # voltar sem erro = o banco ACEITOU a escrita
        raise self.erro

    def erro_do_banco(self, e):
        return isinstance(e, _ErroReadonly)


class _ConnFake:
    """O doctor nunca consulta a conexão direto — só via o dialeto. Só o `rodar` a fecha."""

    def __init__(self):
        self.fechada = False

    def close(self):
        self.fechada = True


def _ctx_com(dialeto, settings=None):
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    ctx.dialeto = dialeto
    ctx.settings = settings
    ctx.conn = _ConnFake()
    return ctx


def test_checar_somente_leitura_ok_quando_o_banco_recusa():
    r = checar_somente_leitura(_ctx_com(_DialetoFake()))
    assert r.ok
    assert "25006" in r.detalhe


def test_checar_somente_leitura_falha_quando_o_probe_volta_sem_erro():
    # Regressão da inversão: o `probar_escrita` sinaliza "escrita aceita" VOLTANDO
    # normalmente (o sentinela de rollback é interno ao dialeto). Se o doctor lesse
    # isso ao contrário, um banco gravável passaria como somente-leitura.
    r = checar_somente_leitura(_ctx_com(_DialetoFake(escrita_aceita=True)))
    assert not r.ok
    assert r.remediacao


def test_checar_somente_leitura_nao_confirma_com_erro_qualquer_do_banco():
    # T4: o veredito vem do predicado `erro_readonly`, não de um `except` largo. Um erro
    # de banco que NÃO é recusa de escrita (tabela já existe, disco cheio, timeout) não
    # pode virar "somente-leitura confirmado" — o cadeado já falha aberta, e um falso
    # positivo aqui esconderia uma conexão gravável.
    d = _DialetoFake(erro=RuntimeError("disco cheio"))
    with pytest.raises(RuntimeError):
        checar_somente_leitura(_ctx_com(d))
    # no doctor de verdade isso vira falha visível ("erro inesperado"), não um OK
    assert rodar([lambda ctx: checar_somente_leitura(_ctx_com(d))], _ctx_com(d), False, False) == 1


def test_checar_auth_le_a_identidade_pelo_dialeto(monkeypatch):
    _limpar_pg(monkeypatch)
    for k, v in {"DB_HOST": "h", "DB_DBNAME": "d", "DB_PASSWORD": "p"}.items():
        monkeypatch.setenv(k, v)
    from db_mcp.config import Settings

    d = _DialetoFake(respostas=lambda sql, params: {"usuario": "mcp_ro", "banco": "demo"})
    d.conectar_doctor = lambda s: object()
    ctx = _ctx_com(d, settings=Settings.load(env_file=None, yaml_file="/nao/existe.yaml"))
    r = checar_auth(ctx)
    assert r.ok
    # apelidos do contrato, não colunas do Postgres: `current_database()` é `database()` no MySQL
    assert "mcp_ro" in r.detalhe and "demo" in r.detalhe
    assert d.cursor.chamadas[0][0] == "SELECT identidade"


def test_checar_allowlist_usa_o_schema_padrao_do_dialeto_e_acha_faltante(monkeypatch):
    _limpar_pg(monkeypatch)
    for k, v in {"DB_HOST": "h", "DB_DBNAME": "d", "DB_PASSWORD": "p"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("ALLOWLIST", '["clientes", "vendas.pedidos"]')
    from db_mcp.config import Settings

    # só a tabela no schema padrão DO DIALETO existe; `vendas.pedidos` não
    def respostas(sql, params):
        return {"existe": 1} if params == ("sch_do_dialeto", "clientes") else None

    d = _DialetoFake(respostas=respostas)
    ctx = _ctx_com(d, settings=Settings.load(env_file=None, yaml_file="/nao/existe.yaml"))
    r = checar_allowlist_existe(ctx)
    assert not r.ok
    assert "vendas.pedidos" in r.detalhe
    # nome sem schema herda o schema_padrao DO DIALETO (era "public" cravado no doctor)
    assert d.cursor.chamadas[0][1] == ("sch_do_dialeto", "clientes")


def test_saida_decorada_degrada_para_ascii(capsys):
    # Regressão: com encoding limitado (emoji=False), as decorações ↳ / — / · eram
    # impressas cruas e quebravam com UnicodeEncodeError (console cp1252 / pipe ascii).
    # Toda a saída decorativa deve ser ASCII quando emoji=False.
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    rodar([_ok, _falha, _pula], ctx, cor=False, emoji=False)
    out = capsys.readouterr().out
    out.encode("ascii")  # não pode levantar UnicodeEncodeError
    assert "->" in out  # a seta ↳ virou ASCII na linha de remediação
