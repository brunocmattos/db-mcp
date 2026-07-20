from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from ..errors import SqlInvalido

if TYPE_CHECKING:
    import psycopg  # só pra tipo: o import de runtime segue lazy dentro dos métodos

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
            host=s.db_host,
            port=s.db_port or 5432,  # default do dialeto Postgres quando db_port é None
            dbname=s.db_dbname,
            user=s.db_user,
            password=s.db_password,
            sslmode=s.db_sslmode,
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
    def _configurar(conn: psycopg.Connection[Any]) -> None:
        conn.read_only = True  # toda transação da conexão é READ ONLY
        # Não deixa o psycopg auto-preparar statements: o `DISCARD ALL` do reset apaga os
        # prepared no servidor, mas o cache do psycopg continuaria apontando pra eles, e a
        # próxima query idêntica (as tools de introspecção mandam SQL fixo) quebraria.
        conn.prepare_threshold = None

    @staticmethod
    def _resetar(conn: psycopg.Connection[Any]) -> None:
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
        """SQL de amostra com o nome CITADO (identify=True), no lugar de interpolar cru.

        O parse `into=exp.Table` é a defesa: ele recusa qualquer coisa que não seja um
        nome de tabela (`t; DROP`, `t WHERE 1=1`, `(SELECT 1)`) — mais estrito que a
        regex que vivia no server.py, e sem o viés de Postgres dela. SqlglotError, não
        ParseError: o tokenizer levanta TokenError, que é irmã e não filha (ver
        guardrails/sql.py). Deixar vazar seria recusa sem auditoria.
        """
        try:
            tab = sqlglot.parse_one(tabela, into=exp.Table, read=self.sqlglot_dialeto)
        except SqlglotError as e:
            raise SqlInvalido(f"nome de tabela inválido: {tabela!r}") from e
        return f"SELECT * FROM {tab.sql(dialect=self.sqlglot_dialeto, identify=True)} LIMIT {n}"

    def sql_probe_escrita(self) -> str:
        return "CREATE TABLE __doctor_write_probe__ (n int)"

    def sql_introspecao(
        self, tipo: str, schema: str | None = None, tabela: str | None = None
    ) -> tuple[str, tuple[Any, ...]]:
        # SQL idêntico ao que vivia inline no server.py (T2). O nome vai por %s; a rota
        # não valida (o %s não parseia no mysql), então nada de sqlglot aqui.
        if tipo == "schemas":
            return (
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name NOT LIKE 'pg_%' AND schema_name <> 'information_schema' "
                "ORDER BY schema_name",
                (),
            )
        if tipo == "tabelas":
            return (
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s AND table_type = 'BASE TABLE' "
                "ORDER BY table_name",
                (schema,),
            )
        if tipo == "views":
            return (
                "SELECT table_name FROM information_schema.views "
                "WHERE table_schema = %s ORDER BY table_name",
                (schema,),
            )
        if tipo == "colunas":
            return (
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s "
                "ORDER BY ordinal_position",
                (schema, tabela),
            )
        raise SqlInvalido(f"tipo de introspecção desconhecido: {tipo!r}")
