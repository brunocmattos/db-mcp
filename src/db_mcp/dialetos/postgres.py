from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import sqlglot
from sqlglot import exp

if TYPE_CHECKING:
    from ..config import Settings
    from .base import PoolLike

# Copiada sem edição de guardrails/sql.py — o mecanismo (exp.Anonymous + nome) fica
# no validador; só a lista é do dialeto.
FUNCS_PROIBIDAS_POSTGRES = frozenset(
    {
        # arquivo / objeto grande / rede
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
        "pg_read_server_files",
        "lo_import",
        "lo_export",
        "lo_get",
        "lo_open",
        "loread",
        "dblink",
        "dblink_exec",
        # escreve WAL durável mesmo em read-only (enche disco / injeta na decodificação lógica)
        "pg_logical_emit_message",
        # outros efeitos colaterais que o read-only do banco não barra
        "pg_notify",
        "pg_export_snapshot",
        "txid_current",
        "pg_current_xact_id",
        # DoS / controle de sessão alheia
        "pg_sleep",
        "pg_sleep_for",
        "pg_sleep_until",
        "pg_terminate_backend",
        "pg_cancel_backend",
        # efeito colateral em sequence
        "nextval",
        "setval",
        # muda o estado da sessão (GUC): statement_timeout, search_path, etc.
        "set_config",
        # advisory locks — efeito colateral que persiste na conexão do pool
        "pg_advisory_lock",
        "pg_advisory_lock_shared",
        "pg_advisory_xact_lock",
        "pg_advisory_xact_lock_shared",
        "pg_try_advisory_lock",
        "pg_try_advisory_lock_shared",
        "pg_try_advisory_xact_lock",
        "pg_try_advisory_xact_lock_shared",
        "pg_advisory_unlock",
        "pg_advisory_unlock_shared",
        "pg_advisory_unlock_all",
        # export XML: recebem tabela/consulta como string e escapam da allowlist
        "query_to_xml",
        "query_to_xmlschema",
        "query_to_xml_and_xmlschema",
        "table_to_xml",
        "table_to_xmlschema",
        "table_to_xml_and_xmlschema",
        "cursor_to_xml",
        "cursor_to_xmlschema",
        "schema_to_xml",
        "schema_to_xmlschema",
        "schema_to_xml_and_xmlschema",
        "database_to_xml",
        "database_to_xmlschema",
        "database_to_xml_and_xmlschema",
    }
)


class DialetoPostgres:
    nome = "postgres"
    sqlglot_dialeto = "postgres"
    funcs_proibidas = FUNCS_PROIBIDAS_POSTGRES
    schema_padrao = "public"

    def __init__(self) -> None:
        import psycopg  # lazy: o extra `postgres` só é exigido de quem usa postgres

        self._psycopg = psycopg
        self.erros_readonly: tuple[type[Exception], ...] = (
            psycopg.errors.InsufficientPrivilege,  # 42501 — role sem privilégio
            psycopg.errors.ReadOnlySqlTransaction,  # 25006 — transação READ ONLY
        )

    def criar_pool(self, s: Settings) -> PoolLike:
        import psycopg
        from psycopg_pool import ConnectionPool

        conninfo = psycopg.conninfo.make_conninfo(
            host=s.pg_host,
            port=s.pg_port,
            dbname=s.pg_dbname,
            user=s.pg_user,
            password=s.pg_password,
            sslmode=s.pg_sslmode,
            application_name="db-mcp",
            options=f"-c statement_timeout={s.statement_timeout_ms} "
            f"-c idle_in_transaction_session_timeout=10000",
        )
        return ConnectionPool(
            conninfo,
            min_size=s.pool_min,
            max_size=s.pool_max,
            configure=self._configurar,
            reset=self._resetar,
            open=True,
        )

    @staticmethod
    def _configurar(conn: Any) -> None:
        conn.read_only = True  # toda transação da conexão é READ ONLY
        # Não deixa o psycopg auto-preparar statements: o `DISCARD ALL` do reset apaga os
        # prepared no servidor, mas o cache do psycopg continuaria apontando pra eles, e a
        # próxima query idêntica (as tools de introspecção mandam SQL fixo) quebraria.
        conn.prepare_threshold = None

    @staticmethod
    def _resetar(conn: Any) -> None:
        # Ao devolver a conexão ao pool, zera todo o estado de sessão (GUCs mudados por
        # `set_config`, advisory locks, temp tables) pra que nada vaze de um cliente pro
        # próximo que reusar a mesma conexão física.
        conn.rollback()
        autocommit = conn.autocommit
        conn.autocommit = True  # DISCARD ALL não roda dentro de uma transação
        try:
            conn.execute("DISCARD ALL")
        finally:
            conn.autocommit = autocommit
            conn.read_only = True  # DISCARD ALL zera o modo read-only; reaplica

    def erro_de_timeout(self, e: Exception) -> bool:
        return isinstance(e, self._psycopg.errors.QueryCanceled)

    def erro_do_banco(self, e: Exception) -> bool:
        return isinstance(e, self._psycopg.Error)

    @contextmanager
    def linhas_como_dict(self, conn: Any) -> Iterator[Any]:
        from psycopg.rows import dict_row

        with conn.cursor(row_factory=dict_row) as cur:
            yield cur

    def sql_amostra(self, tabela: str, n: int) -> str:
        tab = sqlglot.parse_one(tabela, into=exp.Table, read=self.sqlglot_dialeto)
        return f"SELECT * FROM {tab.sql(dialect=self.sqlglot_dialeto, identify=True)} LIMIT {n}"

    def sql_probe_escrita(self) -> str:
        return "CREATE TABLE __doctor_write_probe__ (n int)"
