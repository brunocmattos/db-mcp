from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

    from ..config import Settings
    from .base import PoolLike

# O mecanismo (exp.Anonymous + nome) fica no validador; só a lista é do dialeto.
# Defesa em profundidade: o limite real é o GRANT (medido: CREATE recusa com 262).
# Esta lista existe pro que o GRANT NÃO barra.
#
# Enumerada, NÃO um prefixo "xp_*": um prefixo daria falsa cobertura (as fn_* ficariam
# de fora) e barraria nome de usuário que por acaso comece com xp_.
FUNCS_PROIBIDAS_SQLSERVER = frozenset(
    {
        # saem do banco/instância — o vetor mais grave do SQL Server. MEDIDO: chegam
        # como exp.Anonymous e passam a checagem de raiz; só a blocklist os pega.
        "openquery",
        "opendatasource",
        "openrowset",
        # execução de comando no SO e leitura de disco/registro
        "xp_cmdshell",
        "xp_regread",
        "xp_regwrite",
        "xp_dirtree",
        "xp_fileexist",
        "xp_subdirs",
        "xp_msver",
        # leem trilha de auditoria e trace do servidor
        "fn_get_audit_file",
        "fn_trace_gettable",
        # enumera permissões — reconhecimento
        "fn_my_permissions",
    }
)


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

    def criar_pool(self, s: Settings) -> PoolLike:
        raise NotImplementedError  # Task 3

    def conectar_doctor(self, s: Settings) -> Any:
        raise NotImplementedError  # Task 3

    # --- Placeholders restantes do Protocol Dialeto -----------------------------
    #
    # Sem eles o mypy strict recusa `_sqlserver() -> Dialeto` (Protocol estrutural
    # exige TODOS os membros, não só os que o T1 usa). Cada um preenche na task
    # marcada no comentário; aqui só existem pra o esqueleto tipar como Dialeto de
    # verdade.

    def probar_escrita(self, conn: Any) -> None:
        raise NotImplementedError  # Task 3

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
        raise NotImplementedError  # Task 5

    def sql_identidade(self) -> str:
        raise NotImplementedError  # Task 5

    def sql_introspecao(
        self, tipo: str, schema: str | None = None, tabela: str | None = None
    ) -> tuple[str, tuple[Any, ...]]:
        raise NotImplementedError  # Task 5
