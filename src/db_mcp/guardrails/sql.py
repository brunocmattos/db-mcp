from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from ..errors import SomenteLeitura, SqlInvalido

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

# Funções perigosas (efeito colateral, arquivo, rede, DoS, ou que executam SQL/tabela vindos
# de string e escapam do validador e da allowlist) — bloqueadas por nome.
FUNCS_PROIBIDAS = {
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


def _iter_nos(raiz: exp.Expression) -> Iterator[Any]:
    """Itera todos os nós da árvore (tolerante a diferenças de versão do sqlglot)."""
    for item in raiz.walk():
        yield item[0] if isinstance(item, tuple) else item


def validar_somente_leitura(sql: str) -> None:
    """Levanta SqlInvalido/SomenteLeitura se `sql` não for um único SELECT seguro."""
    try:
        arvores = [
            a
            for a in sqlglot.parse(sql, read="postgres", error_level=sqlglot.ErrorLevel.RAISE)
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
            if fn in FUNCS_PROIBIDAS:
                raise SomenteLeitura(f"função não permitida: {fn}")
