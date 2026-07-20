from __future__ import annotations

from contextlib import AbstractContextManager
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from ..config import Settings


class Perfil(Enum):
    """O que o MCP tem permissão de fazer.

    Existe com um único valor de propósito: a escrita tem spec próprio (ver
    docs/superpowers/specs/2026-07-16-db-mcp-multi-dialeto-design.md, §1). O
    parâmetro está aqui pra costura nascer no lugar certo, não pra ser usada.

    O princípio que vale quando a escrita chegar: a config só pode SUBTRAIR do
    que o usuário do banco já pode fazer, nunca somar. Perfil de escrita num
    usuário read-only continua não escrevendo — o banco recusa.
    """

    SOMENTE_LEITURA = "somente_leitura"


class PoolLike(Protocol):
    """O mínimo que db.py usa de um pool. O psycopg_pool já tem esta forma."""

    def connection(self) -> Any: ...
    def close(self) -> None: ...


class Dialeto(Protocol):
    """O que muda entre bancos. Tudo o mais é dialeto-agnóstico.

    `configurar`/`resetar` NÃO são membros deste contrato de propósito: são detalhe
    de implementação do pool de cada driver (o psycopg os recebe como callback; o
    mysql-connector e o pymssql têm mecanismos diferentes). Quem garante o reset de
    sessão é o `criar_pool` de cada dialeto.
    """

    nome: str
    sqlglot_dialeto: str
    funcs_proibidas: frozenset[str]
    schema_padrao: str
    erros_readonly: tuple[type[Exception], ...]

    def criar_pool(self, s: Settings) -> PoolLike: ...

    def erro_de_timeout(self, e: Exception) -> bool:
        """True se a exceção do driver representa query cortada por timeout."""
        ...

    def erro_do_banco(self, e: Exception) -> bool:
        """True se a exceção veio do driver (vira ErroBanco tratado)."""
        ...

    def linhas_como_dict(self, conn: Any) -> AbstractContextManager[Any]:
        """Cursor que devolve linhas como dict. Usado como `with ... as cur`.

        AbstractContextManager (não Iterator): a impl usa @contextmanager, que
        devolve um context manager. Declarar Iterator aqui quebra o mypy strict.
        """
        ...

    def sql_amostra(self, tabela: str, n: int) -> str: ...

    def sql_probe_escrita(self) -> str:
        """DDL que o doctor tenta e ESPERA que falhe."""
        ...

    def sql_introspecao(
        self, tipo: str, schema: str | None = None, tabela: str | None = None
    ) -> tuple[str, tuple[Any, ...]]:
        """SQL + params de introspecção (tipo: tabelas/views/colunas/schemas).

        Devolve (sql, params): o identificador (schema/tabela) vai por query parameter
        (%s), nunca concatenado — mata a injeção sem regex. Esta rota NÃO passa pelo
        validador (o `%s` não parseia em todo dialeto — mysql dá ParseError): é SQL
        fixo e confiável. Recusa (tipo inválido; ou schema != database no MySQL, Fase 1
        T5) levanta McpDbError, auditado no Nucleo.introspectar.
        """
        ...
