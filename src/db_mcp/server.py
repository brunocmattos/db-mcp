from __future__ import annotations

import json
import time
from typing import Any, cast

from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from fastmcp.server.dependencies import get_access_token

from .config import Settings
from .db import Database
from .dialetos.base import Perfil
from .errors import LimiteDeTaxa, McpDbError, ResultadoGrandeDemais
from .guardrails.policy import checar_allowlist, injetar_limit
from .guardrails.ratelimit import RateLimiter
from .guardrails.sql import validar
from .observability import Auditoria


def _identificar_cliente() -> str:
    """Quem está chamando, pra separar rate limit e auditoria por origem: o
    `client_id` do token no HTTP autenticado, ou 'stdio' quando não há request
    (transporte stdio, testes)."""
    try:
        token = get_access_token()
    except Exception:
        return "stdio"
    if token is not None and token.client_id:
        return token.client_id
    return "stdio"


class Nucleo:
    """Junta guardrails + db. Independente do transporte MCP (testável isolado)."""

    def __init__(self, s: Settings, db: Database | None = None) -> None:
        self.s = s
        self.db = db if db is not None else Database(s)
        self.dialeto = self.db.dialeto
        self.rl = RateLimiter(por_minuto=s.rate_limit_per_min)
        self.aud = Auditoria(s.audit_log_path)

    def consultar(
        self,
        sql: str,
        cliente: str = "stdio",
        aplicar_allowlist: bool = True,
        params: Any = None,
        validar_sql: bool = True,
    ) -> dict[str, Any]:
        # `params` são query parameters do driver (paramstyle %s). A introspecção usa
        # isto para o nome de schema/tabela: o valor do agente vai por `params`, nunca
        # concatenado no SQL — mata a classe de injeção em vez de filtrá-la por regex.
        #
        # `validar_sql=False` é usado SÓ pela introspecção (Nucleo.introspectar): o SQL é
        # fixo/interno e o `%s` NÃO parseia em todo dialeto (medido: mysql dá ParseError),
        # então validar()/injetar_limit() derrubariam a introspecção. É seguro — o
        # identificador já vai por params (zero injeção) e o fetchmany(max_rows) do executar
        # limita as linhas sem o LIMIT. No SQL livre (tool `consultar`), fica True: o cadeado
        # nº 3 nunca é desligado no caminho do usuário.
        t0 = time.perf_counter()
        try:
            if not self.rl.permitir(cliente):
                raise LimiteDeTaxa("muitas consultas — tente novamente em instantes")
            if validar_sql:
                validar(sql, self.dialeto, Perfil.SOMENTE_LEITURA)  # cadeado nº 3 (a)
            if aplicar_allowlist:  # cadeado nº 3 (b)
                checar_allowlist(sql, self.s.allowlist, self.dialeto.sqlglot_dialeto)
            # Pede uma linha a mais que o teto: se ela vier, sabemos que houve corte
            # (senão `truncado` seria sempre False quando o LIMIT é o nosso).
            if validar_sql:
                sql_limitado = injetar_limit(sql, self.s.max_rows + 1, self.dialeto.sqlglot_dialeto)
            else:
                sql_limitado = sql  # introspecção: SQL fixo, sem LIMIT (o fetchmany limita)
            linhas, truncado = self.db.executar(sql_limitado, self.s.max_rows, params)
            ms = (time.perf_counter() - t0) * 1000
            # Teto sobre o tamanho da RESPOSTA, checado depois de serializar. `max_rows` já
            # limita a contagem de linhas; isto não é um limite de pico de memória.
            tamanho = len(json.dumps(linhas, default=str).encode("utf-8"))
            if tamanho > self.s.max_result_bytes:
                raise ResultadoGrandeDemais(
                    f"resultado de {tamanho} bytes excede o teto de {self.s.max_result_bytes}"
                )
        except McpDbError as e:
            # Toda recusa (escrita, fora da allowlist, rate limit, timeout, grande demais)
            # deixa rastro na auditoria antes de propagar — é o que mais importa na trilha.
            self.aud.registrar(
                cliente=cliente,
                sql=sql,
                linhas=0,
                ms=(time.perf_counter() - t0) * 1000,
                veredito=e.codigo,
            )
            raise
        self.aud.registrar(cliente=cliente, sql=sql, linhas=len(linhas), ms=ms, veredito="ok")
        return {"linhas": linhas, "truncado": truncado, "total": len(linhas)}

    def amostrar(self, tabela: str, n: int = 10, cliente: str = "stdio") -> dict[str, Any]:
        """Primeiras N linhas de uma tabela liberada (n clampado ao teto; passa pela allowlist).

        O SQL vem do dialeto, não montado aqui: o dialeto cita o nome (identify=True) e
        recusa o que não for uma tabela — mais estrito e sem viés de Postgres que a antiga
        regex. Se o nome for inválido, o SqlInvalido do dialeto é AUDITADO aqui antes de
        propagar. Antes isto vivia na tool, onde o build era avaliado como ARGUMENTO de
        `consultar` e levantava FORA do except que audita — a recusa saía sem rastro.
        """
        t0 = time.perf_counter()
        n = min(max(n, 0), self.s.max_rows)  # clampa: n negativo viraria LIMIT -5 (erro cru)
        try:
            sql = self.dialeto.sql_amostra(tabela, n)
        except McpDbError as e:
            self.aud.registrar(
                cliente=cliente,
                sql=f"amostra(tabela={tabela!r}, n={n})",
                linhas=0,
                ms=(time.perf_counter() - t0) * 1000,
                veredito=e.codigo,
            )
            raise
        return self.consultar(sql, cliente=cliente)

    def introspectar(
        self,
        tipo: str,
        schema: str | None = None,
        tabela: str | None = None,
        cliente: str = "stdio",
    ) -> dict[str, Any]:
        """Introspecção auditada: monta o SQL do dialeto (identificador via params) e roda
        pelo `consultar` SEM validar (SQL fixo; o `%s` não parseia em todo dialeto).

        O schema default vem do dialeto (`schema_padrao`) quando não informado. Se a
        geração do SQL recusar (tipo inválido; ou schema != database no MySQL, Fase 1 T5),
        o McpDbError é AUDITADO aqui antes de propagar, espelhando `amostrar`.
        """
        if schema is None and tipo != "schemas":
            schema = self.dialeto.schema_padrao
        t0 = time.perf_counter()
        try:
            sql, params = self.dialeto.sql_introspecao(tipo, schema=schema, tabela=tabela)
        except McpDbError as e:
            self.aud.registrar(
                cliente=cliente,
                sql=f"introspeccao(tipo={tipo!r}, schema={schema!r}, tabela={tabela!r})",
                linhas=0,
                ms=(time.perf_counter() - t0) * 1000,
                veredito=e.codigo,
            )
            raise
        # params=() (introspecção de schemas, sem binds) vira None: o psycopg/mysql só
        # interpola `%` quando params é sequência, e o LIKE 'pg_%' quebraria a interpolação.
        return self.consultar(
            sql,
            cliente=cliente,
            aplicar_allowlist=False,
            params=params or None,
            validar_sql=False,
        )


def construir_servidor(s: Settings, conectar: bool = True) -> FastMCP:
    # Auth só vale no transporte HTTP; o FastMCP a ignora no stdio. Sem AUTH_TOKEN,
    # auth=None — e o cli recusa subir em HTTP sem token (ver cli.main).
    auth = (
        StaticTokenVerifier(tokens={s.auth_token: {"client_id": "db-mcp", "scopes": ["read"]}})
        if s.auth_token
        else None
    )
    mcp = FastMCP(name="db-mcp", auth=auth)
    if not conectar:  # usado nos testes (não abre conexão com o banco)
        return mcp
    nucleo = Nucleo(s)

    # Introspecção: SQL fixo do dialeto (information_schema), roda auditada pelo Nucleo
    # SEM validar (o `%s` não parseia em todo dialeto) — o identificador vai por params.
    # `schema=None` (não "public") é o default: quem sabe o schema padrão é o DIALETO
    # (no MySQL é o database configurado, não uma constante). Com "public" cravado aqui,
    # toda chamada sem argumento seria recusada no MySQL.
    @mcp.tool
    def listar_schemas() -> list[dict[str, Any]]:
        """Lista os schemas do banco."""
        return cast(
            "list[dict[str, Any]]",
            nucleo.introspectar("schemas", cliente=_identificar_cliente())["linhas"],
        )

    @mcp.tool
    def listar_tabelas(schema: str | None = None) -> list[dict[str, Any]]:
        """Lista as tabelas de um schema."""
        return cast(
            "list[dict[str, Any]]",
            nucleo.introspectar("tabelas", schema=schema, cliente=_identificar_cliente())["linhas"],
        )

    @mcp.tool
    def listar_views(schema: str | None = None) -> list[dict[str, Any]]:
        """Lista as views de um schema."""
        return cast(
            "list[dict[str, Any]]",
            nucleo.introspectar("views", schema=schema, cliente=_identificar_cliente())["linhas"],
        )

    @mcp.tool
    def descrever_tabela(tabela: str, schema: str | None = None) -> list[dict[str, Any]]:
        """Colunas e tipos de uma tabela."""
        return cast(
            "list[dict[str, Any]]",
            nucleo.introspectar(
                "colunas", schema=schema, tabela=tabela, cliente=_identificar_cliente()
            )["linhas"],
        )

    @mcp.tool
    def amostra(tabela: str, n: int = 10) -> dict[str, Any]:
        """Primeiras N linhas de uma tabela liberada (n limitado ao teto; passa pela allowlist)."""
        try:
            return nucleo.amostrar(tabela, n, cliente=_identificar_cliente())
        except McpDbError as e:
            return {"erro": e.codigo, "detalhe": str(e)}

    if s.allow_freeform_sql:

        @mcp.tool
        def consultar(sql: str) -> dict[str, Any]:
            """Executa um SELECT (somente-leitura, validado, allowlist e limitado)."""
            try:
                return nucleo.consultar(sql, cliente=_identificar_cliente())
            except McpDbError as e:
                return {"erro": e.codigo, "detalhe": str(e)}

    return mcp
