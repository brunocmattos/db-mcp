from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from ..errors import SomenteLeitura, SqlInvalido

if TYPE_CHECKING:
    from ..dialetos import Dialeto
    from ..dialetos.base import Perfil

# Nomes de classe (nós do sqlglot) que representam escrita/DDL/utilitários — proibidos.
TAGS_PROIBIDAS = {
    "Insert",
    "Update",
    "Delete",
    "Merge",
    "Create",
    "Drop",
    "Alter",
    "AlterTable",
    "TruncateTable",
    "Command",
    "Set",
    "Grant",
    "Copy",
    "Analyze",
    "Vacuum",
    "Into",  # SELECT ... INTO cria tabela
    "Lock",  # SELECT ... FOR UPDATE/SHARE adquire lock de escrita
}


def _iter_nos(raiz: exp.Expression) -> Iterator[Any]:
    """Itera todos os nós da árvore (tolerante a diferenças de versão do sqlglot)."""
    for item in raiz.walk():
        yield item[0] if isinstance(item, tuple) else item


def validar(sql: str, dialeto: Dialeto, perfil: Perfil) -> None:
    """Levanta SqlInvalido/SomenteLeitura se `sql` não for um único SELECT seguro.

    `perfil` só tem um valor nesta fase (SOMENTE_LEITURA) — a escrita tem spec
    própria. O parâmetro existe pra costura nascer no lugar certo.
    """
    try:
        arvores = [
            a
            for a in sqlglot.parse(
                sql, read=dialeto.sqlglot_dialeto, error_level=sqlglot.ErrorLevel.RAISE
            )
            if a is not None
        ]
    except ParseError as e:
        raise SqlInvalido(f"SQL inválido: {e}") from e

    if len(arvores) != 1:
        raise SqlInvalido("apenas uma instrução SQL é permitida")

    raiz = arvores[0]
    # SetOperation cobre UNION, INTERSECT e EXCEPT — todos só-leitura.
    if not isinstance(raiz, (exp.Select, exp.SetOperation)):
        raise SomenteLeitura("apenas comandos SELECT são permitidos")

    for node in _iter_nos(raiz):
        nome_no = type(node).__name__
        if nome_no in TAGS_PROIBIDAS:
            raise SomenteLeitura(f"comando não permitido: {nome_no}")
        if isinstance(node, exp.Anonymous):
            # node.name devolve o nome nu mesmo com aspas (`"pg_read_file"`) ou schema
            # (`pg_catalog.pg_read_file`) — str(node.this) traria as aspas e escaparia a lista.
            fn = node.name.lower()
            if fn in dialeto.funcs_proibidas:
                raise SomenteLeitura(f"função não permitida: {fn}")
