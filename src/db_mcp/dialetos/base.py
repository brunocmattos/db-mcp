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
    porta_padrao: int  # 5432≠3306: `db_port` é opcional e cada dialeto aplica a sua

    @property
    def schema_padrao(self) -> str:
        """Schema assumido quando o cliente não informa um.

        Propriedade (somente leitura), não atributo: no Postgres é a constante
        `"public"`, mas no MySQL SCHEMA é sinônimo de DATABASE — o padrão é o database
        configurado, que só se conhece pelo `Settings`. Um atributo de classe forçaria
        o dialeto MySQL a fingir uma constante que ele não tem.
        """
        ...

    def criar_pool(self, s: Settings) -> PoolLike: ...

    def erro_readonly(self, e: Exception) -> bool:
        """True se a exceção do driver significa "escrita recusada por ser read-only".

        Predicado, não tupla de classes: o mysql-connector não dá classe própria aos
        erros 1792 (read-only transaction) e 1142 (sem privilégio) — distingui-los exige
        olhar o `.errno`. Casar por classe base lá pegaria erro de banco QUALQUER e o
        doctor daria "somente-leitura confirmado" para uma conexão gravável — o falso
        positivo perigoso, no cadeado que já falha aberta.
        """
        ...

    def conectar_doctor(self, s: Settings) -> Any:
        """Conexão avulsa (fora do pool) para o doctor, em autocommit.

        Fora do pool de propósito: o doctor checa a saúde da configuração antes de
        o servidor existir, e o probe de escrita precisa de uma sessão que ele
        controle. Erro de conexão/autenticação sobe cru — o doctor decide com
        `erro_do_banco`.
        """
        ...

    def probar_escrita(self, conn: Any) -> None:
        """Roda o `sql_probe_escrita` e VOLTA se o banco ACEITOU a escrita (ruim).

        Se o banco recusar, deixa o erro do driver subir — quem classifica é o
        doctor, por `erros_readonly`. A impl é responsável por não deixar nada
        gravado quando a escrita passa (o Postgres reverte a transação; o MySQL
        fará o seu na T5 — lá o DDL tem commit implícito).
        """
        ...

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

    def sql_identidade(self) -> str:
        """SELECT de UMA linha com quem/onde estamos conectados.

        Deve nomear as colunas `usuario` e `banco` (o doctor lê por essas chaves):
        o `current_database()` do Postgres é `database()` no MySQL, então sem apelido
        a chave do dict mudaria junto com o dialeto.
        """
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
