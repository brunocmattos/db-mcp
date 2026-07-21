from __future__ import annotations

from collections.abc import Callable, Iterator
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
#
# Defesa em profundidade: o limite real é o GRANT (medido: CREATE recusa com 262). Esta
# lista NÃO existe porque o GRANT mínimo falha — com GRANT SELECT em tabela específica,
# medido, as fn_* já são recusadas (Msg 300/8189/229). Ela existe porque o GRANT do mundo
# real costuma ser mais largo que o mínimo (db_datareader, login herdado, papel de outro
# sistema), e nesse cenário ela é a única coisa de pé. Errar pra menos aqui é caro.
#
# Enumerada, NÃO um prefixo "xp_*": um prefixo daria falsa cobertura (as fn_* ficariam
# de fora) e barraria nome de usuário que por acaso comece com xp_.
FUNCS_PROIBIDAS_SQLSERVER = frozenset(
    {
        # saem do banco/instância via loopback — o vetor mais grave do SQL Server.
        # MEDIDO: chegam como exp.Anonymous e passam a checagem de raiz Select; aqui
        # é a blocklist quem de fato pega (openrowset na forma padrão de 3 argumentos
        # tem teste dedicado provando isso — as outras variações, com credencial via
        # ';' ou BULK, morrem só de ParseError, ver test_recusados_hoje_apenas_por_parseerror).
        "openquery",
        "opendatasource",
        "openrowset",
        # 🛡️ SOBRA-DEFESA, não vetor real: xp_* são stored procedures ESTENDIDAS, e o
        # motor só as invoca via EXEC — nunca como função/rowset dentro de um SELECT.
        # MEDIDO contra SQL Server 2022 real, como `sa` (sem depender de GRANT):
        #   SELECT * FROM xp_cmdshell('dir')  -> Msg 208 Invalid object name
        #   SELECT xp_cmdshell('dir')         -> Msg 195 not a recognized built-in
        #                                         function name
        # A forma de ataque real (`EXEC xp_cmdshell ...`) já morre na checagem de raiz
        # (não é Select/SetOperation) — a blocklist nem chega a ser acionada. Mantidas
        # enumeradas assim mesmo: sobra-defesa é barata, e errar pra menos não é.
        "xp_cmdshell",
        "xp_regread",
        "xp_regwrite",
        "xp_dirtree",
        "xp_fileexist",
        "xp_subdirs",
        "xp_msver",
        # leem trilha de auditoria, trace e log de transação do servidor. MEDIDO: com
        # usuário restrito dão Msg 300 (fn_get_audit_file), Msg 8189 (fn_trace_gettable)
        # e Msg 229 (fn_dblog/fn_dump_dblog) — mas todas parseiam como Anonymous e são
        # chamáveis por SELECT puro, então aqui, como no grupo do loopback acima, é a
        # blocklist quem realmente pega.
        "fn_get_audit_file",
        "fn_trace_gettable",
        "fn_dblog",
        "fn_dump_dblog",
        # enumera permissões — reconhecimento
        "fn_my_permissions",
    }
)


# Escrita recusada:
#   262  — CREATE TABLE permission denied in database. MEDIDO no SQL Server 2022 /
#          pymssql 2.3.13.
#   3906 — Failed to update database because it is read-only. NÃO MEDIDO — veio da
#          documentação da Microsoft (mensagem do erro 3906). Falha de processo deste
#          projeto deixar isso sem marcar; corrigido aqui em vez de rotular como medido.
#
# ⚠️ O 229 (permission denied on the object) fica DE FORA de propósito: é genérico e
# também sobe por falta de SELECT. Casá-lo faria o doctor confirmar "somente-leitura"
# para conexão que falhou por outro motivo — e aqui o GRANT é o ÚNICO cadeado, porque
# o SQL Server não tem read-only de sessão (medido: SET TRANSACTION READ ONLY dá 156).
NUMEROS_READONLY = frozenset({262, 3906})

# Timeout de query, MEDIDO (pymssql 2.3.13 / SQL Server 2022):
#   args[0] = 20047  "DBPROCESS is dead or not enabled"    <- genérico, qualquer conexão morta
#   texto   = 20003  "Adaptive Server connection timed out" <- o que realmente identifica
# O número do timeout NÃO chega em args[0]. Escrever 20003 na constante faria um predicado
# que nunca casa; casar só 20047 classificaria queda de rede como timeout. Exigimos os dois.
NUMERO_CONEXAO_MORTA = 20047
MARCA_TIMEOUT = b"20003"


class _ConexaoPorConsulta:
    """`PoolLike` sem pool: cada `.connection()` abre uma conexão nova.

    O pymssql não tem pool (medido) e o SQL Server não tem reset de sessão — não existe
    `DISCARD ALL` nem `RESET CONNECTION`. Reusar conexão aqui exigiria reimplementar à mão
    justamente a peça que falhou ABERTA e em silêncio no MySQL (`pool_reset_session`
    zerando o read-only). Conexão nova É o reset.

    Custo medido: handshake ~14,3 ms (15,61 ms conexão nova vs 1,28 ms reusada), ~1% do
    round-trip percebido numa consulta via MCP.
    """

    def __init__(self, conectar: Callable[[], Any]) -> None:
        self._conectar = conectar

    @contextmanager
    def connection(self) -> Iterator[Any]:
        conn = self._conectar()
        try:
            yield conn
        finally:
            conn.close()  # sem pool: close() FECHA de verdade

    def close(self) -> None:
        """No-op: não há nada retido. Existe só para satisfazer `PoolLike`."""


class DialetoSqlServer:
    # 🪤 nome != sqlglot_dialeto. No sqlglot o SQL Server é "tsql"; "sqlserver" levanta
    # ValueError em TODA query — e uma recusa que não é McpDbError escapa da auditoria.
    nome = "sqlserver"
    sqlglot_dialeto = "tsql"
    funcs_proibidas = FUNCS_PROIBIDAS_SQLSERVER
    porta_padrao = 1433

    def __init__(self) -> None:
        import pymssql  # lazy: o extra `sqlserver` só é exigido de quem usa SQL Server

        self._pymssql = pymssql

    @property
    def schema_padrao(self) -> str:
        return "dbo"

    def _conectar(self, s: Settings) -> Any:
        return self._pymssql.connect(
            server=s.db_host,
            # o stub do pymssql tipa `port` como str (medido: as 3 sobrecargas de
            # `connect` em _pymssql.pyi declaram `port: str = ...`) — sem o str() o
            # mypy recusa por nenhuma sobrecarga bater com int.
            port=str(s.db_port or self.porta_padrao),
            database=s.db_dbname,
            user=s.db_user,
            password=s.db_password,
            autocommit=True,
            login_timeout=5,
            # timeout de query é client-side: não existe statement_timeout de servidor
            # como no Postgres nem max_execution_time como no MySQL. O max(1, ...) não é
            # só arredondamento: no pymssql `timeout=0` significa SEM timeout (medido no
            # docstring de `connect`), então statement_timeout_ms < 1000 truncado por
            # divisão inteira viraria 0 e desligaria o timeout em silêncio — o mesmo
            # padrão de falha ABERTA da Fase 1. Arredondar pra cima (timeout > pedido)
            # é o preço aceitável pra nunca cair nesse 0.
            timeout=max(1, s.statement_timeout_ms // 1000),
        )

    def criar_pool(self, s: Settings) -> PoolLike:
        return _ConexaoPorConsulta(lambda: self._conectar(s))

    def conectar_doctor(self, s: Settings) -> Any:
        # ⚠️ Mesma conexão de sempre, sem nenhum cadeado de aplicação — porque não existe
        # nenhum (medido: SET TRANSACTION READ ONLY dá erro 156, sintaxe inválida). O doctor
        # verifica o cadeado nº 1 (o GRANT); se ele mesmo trancasse a sessão, o probe
        # testaria o próprio cadeado e um usuário gravável passaria como "somente-leitura".
        return self._conectar(s)

    def probar_escrita(self, conn: Any) -> None:
        cur = conn.cursor()
        try:
            cur.execute(self.sql_probe_escrita())
            # Chegou aqui = a escrita PASSOU (usuário mal configurado). Limpa o resíduo;
            # best-effort, porque o diagnóstico ruim já é o que importa.
            with suppress(Exception):
                cur.execute("DROP TABLE __doctor_write_probe__")
        finally:
            cur.close()

    def _numero(self, e: Exception) -> int | None:
        """Número do erro DB-Lib. O pymssql o entrega em `e.args[0]`."""
        args: tuple[Any, ...] = getattr(e, "args", ())
        return args[0] if args and isinstance(args[0], int) else None

    def erro_readonly(self, e: Exception) -> bool:
        return isinstance(e, self._pymssql.Error) and self._numero(e) in NUMEROS_READONLY

    def erro_de_timeout(self, e: Exception) -> bool:
        if not isinstance(e, self._pymssql.Error) or self._numero(e) != NUMERO_CONEXAO_MORTA:
            return False
        args: tuple[Any, ...] = getattr(e, "args", ())
        texto = args[1] if len(args) > 1 else b""
        if isinstance(texto, str):
            texto = texto.encode("utf-8", "replace")
        return MARCA_TIMEOUT in texto

    def erro_do_banco(self, e: Exception) -> bool:
        return isinstance(e, self._pymssql.Error)

    @contextmanager
    def linhas_como_dict(self, conn: Any) -> Iterator[Any]:
        cur = conn.cursor(as_dict=True)
        try:
            yield cur
        finally:
            cur.close()

    def sql_amostra(self, tabela: str, n: int) -> str:
        # SqlglotError (não ParseError): o tokenizer levanta TokenError, que é IRMÃ e não
        # filha — deixar vazar seria recusa sem auditoria (o bug corrigido no 74aba49).
        try:
            tab = sqlglot.parse_one(tabela, into=exp.Table, read=self.sqlglot_dialeto)
        except SqlglotError as e:
            raise SqlInvalido(f"nome de tabela inválido: {tabela!r}") from e
        nome = tab.sql(dialect=self.sqlglot_dialeto, identify=True)
        return f"SELECT TOP {n} * FROM {nome}"

    def sql_probe_escrita(self) -> str:
        # CREATE TABLE, não INSERT: o CREATE dá 262 (inequívoco), o INSERT dá 229
        # (genérico). Ver NUMEROS_READONLY.
        return "CREATE TABLE __doctor_write_probe__ (n int)"

    def sql_identidade(self) -> str:
        # MEDIDO contra SQL Server 2022: devolve ('sa', 'master'). `current_database()` do
        # Postgres é `database()` no MySQL e `DB_NAME()` aqui — os apelidos `usuario`/`banco`
        # são o contrato que mantém a chave do dict igual entre dialetos.
        return "SELECT SUSER_SNAME() AS usuario, DB_NAME() AS banco"

    def sql_introspecao(
        self, tipo: str, schema: str | None = None, tabela: str | None = None
    ) -> tuple[str, tuple[Any, ...]]:
        # Diferente do MySQL: aqui schema é schema DE VERDADE (dbo, etc.) dentro do
        # database, então information_schema.schemata é seguro — lista os schemas do
        # banco corrente, não os bancos da instância.
        if tipo == "schemas":
            return (
                "SELECT schema_name AS schema_name FROM information_schema.schemata "
                "ORDER BY schema_name",
                (),
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
