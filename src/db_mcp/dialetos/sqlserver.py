from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

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

    # --- Placeholders restantes do Protocol Dialeto -----------------------------
    #
    # Sem eles o mypy strict recusa `_sqlserver() -> Dialeto` (Protocol estrutural
    # exige TODOS os membros, não só os que o T1 usa). Cada um preenche na task
    # marcada no comentário; aqui só existem pra o esqueleto tipar como Dialeto de
    # verdade.

    def probar_escrita(self, conn: Any) -> None:
        raise NotImplementedError  # Task 4

    def erro_readonly(self, e: Exception) -> bool:
        raise NotImplementedError  # Task 4

    def erro_de_timeout(self, e: Exception) -> bool:
        raise NotImplementedError  # Task 4

    def erro_do_banco(self, e: Exception) -> bool:
        raise NotImplementedError  # Task 4

    def linhas_como_dict(self, conn: Any) -> AbstractContextManager[Any]:
        raise NotImplementedError  # Task 5

    def sql_amostra(self, tabela: str, n: int) -> str:
        raise NotImplementedError  # Task 5

    def sql_probe_escrita(self) -> str:
        raise NotImplementedError  # Task 4

    def sql_identidade(self) -> str:
        raise NotImplementedError  # Task 5

    def sql_introspecao(
        self, tipo: str, schema: str | None = None, tabela: str | None = None
    ) -> tuple[str, tuple[Any, ...]]:
        raise NotImplementedError  # Task 5
