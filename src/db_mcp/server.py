from __future__ import annotations

import json
import re
import time
from typing import Any, cast

from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from fastmcp.server.dependencies import get_access_token

from .config import Settings
from .db import Database
from .dialetos.base import Perfil
from .errors import LimiteDeTaxa, McpDbError, ResultadoGrandeDemais, SqlInvalido
from .guardrails.policy import checar_allowlist, injetar_limit
from .guardrails.ratelimit import RateLimiter
from .guardrails.sql import validar
from .observability import Auditoria

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


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


def _validar_ident(nome: str) -> str:
    """Valida um identificador simples (schema ou tabela). Bloqueia injeção de SQL
    nas ferramentas de introspecção, que interpolam o nome direto na query."""
    if not _IDENT.match(nome or ""):
        raise SqlInvalido(f"identificador inválido: {nome!r}")
    return nome


def _validar_qualificado(nome: str) -> str:
    """Valida 'tabela' ou 'schema.tabela'. Bloqueia injeção de SQL na ferramenta amostra."""
    partes = (nome or "").split(".")
    if len(partes) > 2 or not all(_IDENT.match(p) for p in partes):
        raise SqlInvalido(f"nome de tabela inválido: {nome!r}")
    return nome


class Nucleo:
    """Junta guardrails + db. Independente do transporte MCP (testável isolado)."""

    def __init__(self, s: Settings, db: Database | None = None) -> None:
        self.s = s
        self.db = db if db is not None else Database(s)
        self.dialeto = self.db.dialeto
        self.rl = RateLimiter(por_minuto=s.rate_limit_per_min)
        self.aud = Auditoria(s.audit_log_path)

    def consultar(
        self, sql: str, cliente: str = "stdio", aplicar_allowlist: bool = True
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        try:
            if not self.rl.permitir(cliente):
                raise LimiteDeTaxa("muitas consultas — tente novamente em instantes")
            validar(sql, self.dialeto, Perfil.SOMENTE_LEITURA)  # cadeado nº 3 (a)
            if aplicar_allowlist:
                checar_allowlist(sql, self.s.allowlist)  # cadeado nº 3 (b)
            # Pede uma linha a mais que o teto: se ela vier, sabemos que houve corte
            # (senão `truncado` seria sempre False quando o LIMIT é o nosso).
            sql_limitado = injetar_limit(sql, self.s.max_rows + 1)
            linhas, truncado = self.db.executar(sql_limitado, self.s.max_rows)
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

    # Introspecção: SQL fixo em information_schema → aplicar_allowlist=False
    @mcp.tool
    def listar_schemas() -> list[dict[str, Any]]:
        """Lista os schemas do banco."""
        return cast(
            "list[dict[str, Any]]",
            nucleo.consultar(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name NOT LIKE 'pg_%' AND schema_name <> 'information_schema' "
                "ORDER BY schema_name",
                cliente=_identificar_cliente(),
                aplicar_allowlist=False,
            )["linhas"],
        )

    @mcp.tool
    def listar_tabelas(schema: str = "public") -> list[dict[str, Any]]:
        """Lista as tabelas de um schema."""
        _validar_ident(schema)
        return cast(
            "list[dict[str, Any]]",
            nucleo.consultar(
                f"SELECT table_name FROM information_schema.tables "
                f"WHERE table_schema = '{schema}' AND table_type = 'BASE TABLE' "
                f"ORDER BY table_name",
                cliente=_identificar_cliente(),
                aplicar_allowlist=False,
            )["linhas"],
        )

    @mcp.tool
    def listar_views(schema: str = "public") -> list[dict[str, Any]]:
        """Lista as views de um schema."""
        _validar_ident(schema)
        return cast(
            "list[dict[str, Any]]",
            nucleo.consultar(
                f"SELECT table_name FROM information_schema.views "
                f"WHERE table_schema = '{schema}' ORDER BY table_name",
                cliente=_identificar_cliente(),
                aplicar_allowlist=False,
            )["linhas"],
        )

    @mcp.tool
    def descrever_tabela(tabela: str, schema: str = "public") -> list[dict[str, Any]]:
        """Colunas e tipos de uma tabela."""
        _validar_ident(schema)
        _validar_ident(tabela)
        return cast(
            "list[dict[str, Any]]",
            nucleo.consultar(
                f"SELECT column_name, data_type, is_nullable "
                f"FROM information_schema.columns "
                f"WHERE table_schema = '{schema}' AND table_name = '{tabela}' "
                f"ORDER BY ordinal_position",
                cliente=_identificar_cliente(),
                aplicar_allowlist=False,
            )["linhas"],
        )

    @mcp.tool
    def amostra(tabela: str, n: int = 10) -> dict[str, Any]:
        """Primeiras N linhas de uma tabela liberada (n limitado ao teto; passa pela allowlist)."""
        try:
            _validar_qualificado(tabela)
            n = min(max(n, 0), s.max_rows)  # clampa: n negativo viraria LIMIT -5 (erro cru)
            return nucleo.consultar(
                f"SELECT * FROM {tabela} LIMIT {n}", cliente=_identificar_cliente()
            )
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
