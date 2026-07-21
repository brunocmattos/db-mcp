from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING, Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from ..errors import SqlInvalido

if TYPE_CHECKING:
    from ..config import Settings
    from .base import PoolLike

# O mecanismo (exp.Anonymous + nome) fica no validador; só a lista é do dialeto.
# Defesa em profundidade: o limite real é o `GRANT SELECT` (medido: recusa CREATE/
# INSERT/UPDATE/DELETE com errno 1142). Esta lista existe pro que o GRANT NÃO barra —
# funções que leem arquivo, seguram a sessão ou derrubam o servidor sem escrever nada.
FUNCS_PROIBIDAS_MYSQL = frozenset(
    {
        # lê arquivo do servidor (o vetor clássico do MySQL; exige FILE, mas a defesa
        # não pode depender de o GRANT estar certo)
        "load_file",
        # DoS: seguram a conexão do pool
        "sleep",
        "benchmark",
        # locks nomeados — efeito colateral que PERSISTE na conexão do pool. São funções
        # PADRÃO do MySQL (não precisam de UDF), viram exp.Anonymous e passariam batido:
        # o equivalente exato dos pg_advisory_* da lista do Postgres.
        "get_lock",
        "release_lock",
        "release_all_locks",
        "is_free_lock",
        "is_used_lock",
        # bloqueiam a sessão esperando replicação (DoS silencioso)
        "master_pos_wait",
        "source_pos_wait",
        # UDFs do lib_mysqludf_sys: execução de comando no SO. Não são padrão (quase
        # nunca instaladas), mas quando estão, são game over.
        "sys_exec",
        "sys_eval",
    }
)

# Escrita recusada, MEDIDO no MySQL 8.4 / mysql-connector 9.7:
#   1142 (42000) — o GRANT não permite (CREATE/INSERT/UPDATE/DELETE sem privilégio)
#   1792 (25006) — a transação é READ ONLY (CREATE TABLE com SET SESSION TRANSACTION
#                  READ ONLY ligado; o mesmo SQLSTATE do 25006 do Postgres)
# Sem classe própria no driver — os dois chegam como ProgrammingError, e casar por
# classe pegaria erro de banco QUALQUER. Daí `erro_readonly` ser predicado (T4).
ERRNOS_READONLY = frozenset({1792, 1142})

ERRNO_TIMEOUT = 3024  # ER_QUERY_TIMEOUT — max_execution_time estourou


class _PoolMySQL:
    """Adaptador: o `MySQLConnectionPool` cru só tem `get_connection()`/`close()`,
    e o contrato `PoolLike` pede `.connection()` como context manager.

    🔴 O ponto crítico de segurança do dialeto mora aqui. MEDIDO (mysql-connector 9.7,
    MySQL 8.4): com `pool_reset_session=True`, o retorno da conexão ao pool **ZERA** o
    `SET SESSION TRANSACTION READ ONLY` (mesmo CONNECTION_ID, valor 1 → 0) e o
    `max_execution_time` (4321 → 0). Aplicá-los uma vez na criação do pool falharia
    ABERTO: a partir do 2º checkout as conexões voltariam graváveis e sem timeout, em
    silêncio. Por isso a reaplicação é POR CHECKOUT, e não um detalhe de estilo.

    Diferente do Postgres, onde `default_transaction_read_only` no role faz o servidor
    garantir isso sozinho — aqui o cinto é da aplicação. O suspensório (GRANT SELECT)
    é o que segura se este código falhar.
    """

    def __init__(self, pool: Any, statement_timeout_ms: int) -> None:
        self._pool = pool
        self._timeout_ms = statement_timeout_ms

    @contextmanager
    def connection(self) -> Iterator[Any]:
        cnx = self._pool.get_connection()
        try:
            cur = cnx.cursor()
            try:
                cur.execute("SET SESSION TRANSACTION READ ONLY")
                cur.execute(f"SET SESSION max_execution_time = {int(self._timeout_ms)}")
            finally:
                cur.close()
            yield cnx
        finally:
            cnx.close()  # no pool do mysql-connector, close() DEVOLVE ao pool

    def close(self) -> None:
        # O MySQLConnectionPool não expõe um close() público (o `close` da API é o da
        # conexão, que devolve ao pool). `_remove_connections` é o único jeito de fechar
        # os sockets de verdade; se a API mudar, não derrubamos o shutdown por isso.
        with suppress(Exception):
            self._pool._remove_connections()


class DialetoMySQL:
    nome = "mysql"
    sqlglot_dialeto = "mysql"
    funcs_proibidas = FUNCS_PROIBIDAS_MYSQL
    porta_padrao = 3306

    def __init__(self) -> None:
        import mysql.connector  # lazy: o extra `mysql` só é exigido de quem usa mysql

        self._mysql = mysql.connector
        self._dbname: str | None = None

    # --- schema == database (§6 do spec) ---------------------------------------
    #
    # No MySQL não existe a hierarquia database > schema do Postgres: SCHEMA é sinônimo
    # de DATABASE. Então o "schema padrão" não é uma constante ("public") — é o database
    # configurado, que só se sabe pelo Settings. Capturado nos dois pontos que recebem
    # Settings (`criar_pool` e `conectar_doctor`), que são os únicos caminhos por onde o
    # dialeto entra em uso.

    @property
    def schema_padrao(self) -> str:
        if self._dbname is None:
            # Preferimos estourar a devolver um schema errado em silêncio: introspecção
            # no schema errado é vazamento de metadados de outro database da instância.
            raise SqlInvalido(
                "dialeto mysql usado antes de conhecer o database "
                "(criar_pool/conectar_doctor não foram chamados)"
            )
        return self._dbname

    def criar_pool(self, s: Settings) -> PoolLike:
        from mysql.connector import pooling

        self._dbname = s.db_dbname
        pool = pooling.MySQLConnectionPool(
            pool_name="db-mcp",
            # o mysql-connector tem teto RÍGIDO de 32 por pool (CNX_POOL_MAXSIZE);
            # pedir mais levanta erro na criação, então clampamos.
            pool_size=max(1, min(s.pool_max, 32)),
            pool_reset_session=True,
            host=s.db_host,
            port=s.db_port or self.porta_padrao,
            database=s.db_dbname,
            user=s.db_user,
            password=s.db_password,
            autocommit=True,
            connection_timeout=5,
        )
        return _PoolMySQL(pool, s.statement_timeout_ms)

    def conectar_doctor(self, s: Settings) -> Any:
        self._dbname = s.db_dbname
        # ⚠️ De propósito SEM `SET SESSION TRANSACTION READ ONLY`. O doctor existe pra
        # verificar o cadeado nº 1 — o usuário DO BANCO. Se ele mesmo trancasse a sessão,
        # o probe testaria o próprio cadeado e um usuário com GRANT de escrita passaria
        # como "somente-leitura confirmado". Medido: só o GRANT já recusa (errno 1142).
        return self._mysql.connect(
            host=s.db_host,
            port=s.db_port or self.porta_padrao,
            database=s.db_dbname,
            user=s.db_user,
            password=s.db_password,
            autocommit=True,
            connection_timeout=5,
        )

    def probar_escrita(self, conn: Any) -> None:
        cur = conn.cursor()
        try:
            cur.execute(self.sql_probe_escrita())
            # Chegou aqui = a escrita PASSOU (usuário mal configurado). No MySQL o DDL
            # faz commit implícito e `rollback()` é no-op: a tabela FICA. Limpamos o
            # resíduo — best-effort, porque o diagnóstico ruim já é o que importa.
            with suppress(Exception):
                cur.execute("DROP TABLE __doctor_write_probe__")
        finally:
            cur.close()

    def erro_readonly(self, e: Exception) -> bool:
        return isinstance(e, self._mysql.Error) and getattr(e, "errno", None) in ERRNOS_READONLY

    def erro_de_timeout(self, e: Exception) -> bool:
        return isinstance(e, self._mysql.Error) and getattr(e, "errno", None) == ERRNO_TIMEOUT

    def erro_do_banco(self, e: Exception) -> bool:
        return isinstance(e, self._mysql.Error)

    @contextmanager
    def linhas_como_dict(self, conn: Any) -> Iterator[Any]:
        cur = conn.cursor(dictionary=True)
        try:
            yield cur
        finally:
            # 🔴 O `consume_results` NÃO é higiene opcional — sem ele o MySQL quebra no
            # caminho MAIS COMUM. MEDIDO: fechar cursor com linhas por ler levanta
            # `InternalError("Unread result found")`, e o `cnx.close()` seguinte falha
            # com "MySQL Connection not available" — mascarando o erro original E
            # VAZANDO a conexão do pool (que nunca é devolvida).
            # E sobra por ler sempre que a consulta tem mais linhas que o teto: o
            # `db.executar` detecta truncagem justamente com fetchmany(n) + fetchone().
            # O psycopg descarta sozinho; o mysql-connector exige que se drene.
            with suppress(Exception):
                conn.consume_results()
            cur.close()

    def sql_amostra(self, tabela: str, n: int) -> str:
        """Igual ao Postgres, só que `identify=True` no mysql emite CRASES.

        SqlglotError (não ParseError): o tokenizer levanta TokenError, que é irmã e não
        filha — deixar vazar seria recusa sem auditoria.
        """
        try:
            tab = sqlglot.parse_one(tabela, into=exp.Table, read=self.sqlglot_dialeto)
        except SqlglotError as e:
            raise SqlInvalido(f"nome de tabela inválido: {tabela!r}") from e
        return f"SELECT * FROM {tab.sql(dialect=self.sqlglot_dialeto, identify=True)} LIMIT {n}"

    def sql_probe_escrita(self) -> str:
        return "CREATE TABLE __doctor_write_probe__ (n int)"

    def sql_identidade(self) -> str:
        # `current_database()` não existe no MySQL — aqui é `database()`. Os apelidos
        # `usuario`/`banco` são o contrato que mantém a chave do dict igual entre dialetos.
        return "SELECT current_user() AS usuario, database() AS banco"

    def sql_introspecao(
        self, tipo: str, schema: str | None = None, tabela: str | None = None
    ) -> tuple[str, tuple[Any, ...]]:
        # Apelidos explícitos em minúscula: no MySQL 8 as colunas do information_schema
        # vêm em MAIÚSCULA, e sem apelido a chave do dict mudaria de dialeto pra dialeto.
        if tipo == "schemas":
            # §6: NUNCA consultar information_schema.schemata — ela lista os databases da
            # INSTÂNCIA inteira, e o MCP está confinado a um. Devolvemos só o configurado.
            return ("SELECT %s AS schema_name", (self.schema_padrao,))
        if schema is not None and schema != self.schema_padrao:
            # §6: no MySQL schema == database, então "outro schema" é "outro database" —
            # fora do confinamento. Recusa é McpDbError, então o Nucleo AUDITA (com o
            # schema tentado na trilha, valor forense) antes de propagar.
            raise SqlInvalido(
                f"schema {schema!r} fora do database configurado ({self.schema_padrao!r}): "
                "no MySQL schema e database são a mesma coisa"
            )
        if tipo == "tabelas":
            return (
                "SELECT table_name AS table_name FROM information_schema.tables "
                "WHERE table_schema = %s AND table_type = 'BASE TABLE' "
                "ORDER BY table_name",
                (schema,),
            )
        if tipo == "views":
            return (
                "SELECT table_name AS table_name FROM information_schema.views "
                "WHERE table_schema = %s ORDER BY table_name",
                (schema,),
            )
        if tipo == "colunas":
            return (
                "SELECT column_name AS column_name, data_type AS data_type, "
                "is_nullable AS is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s "
                "ORDER BY ordinal_position",
                (schema, tabela),
            )
        raise SqlInvalido(f"tipo de introspecção desconhecido: {tipo!r}")
