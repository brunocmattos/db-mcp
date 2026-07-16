from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import Settings
from .errors import ConsultaTimeout, ErroBanco


class Database:
    def __init__(self, s: Settings) -> None:
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
        self.pool = ConnectionPool(
            conninfo,
            min_size=s.pool_min,
            max_size=s.pool_max,
            configure=self._configurar,
            reset=self._resetar,
            open=True,
        )

    @staticmethod
    def _configurar(conn: psycopg.Connection) -> None:
        conn.read_only = True  # toda transação da conexão é READ ONLY
        # Não deixa o psycopg auto-preparar statements: o `DISCARD ALL` do reset apaga os
        # prepared no servidor, mas o cache do psycopg continuaria apontando pra eles, e a
        # próxima query idêntica (as tools de introspecção mandam SQL fixo) quebraria.
        conn.prepare_threshold = None

    @staticmethod
    def _resetar(conn: psycopg.Connection) -> None:
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

    def executar(self, sql: str, max_rows: int) -> tuple[list[dict[str, Any]], bool]:
        """Roda o SQL (já validado) e devolve (linhas, truncado)."""
        try:
            with (
                self.pool.connection() as conn,
                conn.cursor(row_factory=dict_row) as cur,
            ):
                cur.execute(sql)
                linhas = cur.fetchmany(max_rows)
                truncado = cur.fetchone() is not None
            return linhas, truncado
        except psycopg.errors.QueryCanceled as e:
            raise ConsultaTimeout("consulta excedeu o tempo limite") from e
        except psycopg.Error as e:
            # tabela/coluna inexistente, permissão negada, etc. — vira erro tratado
            # (auditável e com código estável) em vez de escapar cru.
            raise ErroBanco(f"erro do banco: {e}") from e

    def close(self) -> None:
        self.pool.close()
