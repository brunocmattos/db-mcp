from __future__ import annotations

from typing import cast

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

from ..errors import ForaDaAllowlist


def _nome(t: exp.Table) -> str:
    """Nome renderizado da tabela, preservando `catalog` e `db` quando existirem.

    O `catalog` entra de propósito. Sem ele, `outrodb.public.clientes` era reduzida a
    `public.clientes` e casava com a entrada de allowlist feita pro banco CORRENTE — o
    cadeado nº 3 liberando um banco que ninguém liberou.
    """
    return ".".join(p for p in (t.catalog, t.db, t.name) if p)


def _tabelas_todas(arvore: exp.Expression) -> set[str]:
    """Modo conservador: toda tabela citada é tratada como real (checa tudo na allowlist)."""
    return {_nome(t) for t in arvore.find_all(exp.Table)}


def tabelas_referenciadas(sql: str, dialeto: str) -> set[str]:
    """Nomes de tabela reais citados na query (qualificados com schema quando houver).

    Usa a análise de escopo do sqlglot pra distinguir tabela do banco de referência a CTE
    (`WITH x AS ...`), respeitando o escopo de verdade — inclusive que um `WITH` não-recursivo
    não deixa um CTE enxergar um irmão definido depois. Se a análise falhar, cai no modo
    conservador (checa todas as tabelas), que erra pro lado seguro.

    `dialeto` é o dialeto do sqlglot ("postgres" | "mysql" | "tsql") e NÃO tem default:
    ler no dialeto errado é ler outra query, e isto alimenta a allowlist (cadeado nº 3b)."""
    arvore = cast(exp.Expression, sqlglot.parse_one(sql, read=dialeto))
    try:
        escopos = traverse_scope(arvore)
    except Exception:
        return _tabelas_todas(arvore)
    nomes: set[str] = set()
    for escopo in escopos:
        for t in escopo.tables:
            fonte = escopo.sources.get(t.alias_or_name)
            if fonte is not None and not isinstance(fonte, exp.Table):
                continue  # resolve pra um CTE/subquery — não é tabela do banco
            nomes.add(_nome(t))
    return nomes


SCHEMAS_SISTEMA = {"information_schema", "pg_catalog"}


def _tabela_permitida(tab: str, permitidas: set[str]) -> bool:
    """Regra da allowlist:
    - entrada QUALIFICADA (`schema.tabela`) libera só aquele par exato — não dá pra
      burlar trocando o schema;
    - entrada NÃO-QUALIFICADA (`tabela`) libera aquele nome em qualquer schema (é uma
      escolha explícita de quem configurou);
    - uma referência sem schema não casa com entrada qualificada (o search_path é
      ambíguo, então negamos por segurança)."""
    if tab in permitidas:  # match exato (qualificado com qualificado, ou simples com simples)
        return True
    nao_qualificadas = {a for a in permitidas if "." not in a}
    return tab.split(".")[-1] in nao_qualificadas


def _recusar_cross_database(sql: str, dialeto: str) -> None:
    """Recusa qualquer referência que nomeie um catalog (banco) — 3 ou 4 partes.

    Invariante do produto: **o db-mcp aponta pra UM banco**. Citar outro é recusado, e a
    regra não olha a config — o que a torna auditável sem saber em que banco estamos.

    Anda por `find_all` e NÃO pela análise de escopo de propósito: um cadeado de segurança
    não pode depender do `traverse_scope`, que tem fallback justamente por poder falhar.
    Um CTE nunca gera falso positivo aqui porque nome de CTE é um identificador único —
    não carrega catalog.

    Medido em 2026-07-21: no Postgres e no MySQL isto é latente (o servidor recusa com
    "cross-database references are not implemented" e com erro 1064), mas o SQL Server
    EXECUTA nome de 3 partes, e o de 4 partes sai da instância via linked server.
    """
    arvore = cast(exp.Expression, sqlglot.parse_one(sql, read=dialeto))
    for t in arvore.find_all(exp.Table):
        if t.catalog:
            raise ForaDaAllowlist(f"referência a outro banco não é permitida: {_nome(t)}")


def checar_allowlist(sql: str, allowlist: list[str], dialeto: str) -> None:
    # Antes do "*": o `*` desliga a ALLOWLIST, não o invariante de um-banco-só. Se ele
    # liberasse cross-database, a proteção sumiria na config mais usada — falha ABERTA
    # justamente no default.
    _recusar_cross_database(sql, dialeto)
    if "*" in allowlist:
        return
    permitidas = set(allowlist)
    for tab in tabelas_referenciadas(sql, dialeto):
        schema = tab.split(".")[0] if "." in tab else None
        if schema in SCHEMAS_SISTEMA:
            continue  # catálogos do sistema (information_schema/pg_catalog) sempre liberados
        if not _tabela_permitida(tab, permitidas):
            raise ForaDaAllowlist(f"tabela não liberada: {tab}")


def injetar_limit(sql: str, teto: int, dialeto: str) -> str:
    """Garante que a query não peça mais que `teto` linhas. Se já houver um limite
    literal dentro do teto, respeita sem mexer; qualquer outra forma (sem limite, `LIMIT ALL`,
    limite gigante ou não-literal, `FETCH FIRST n ROWS`) é normalizada pro teto.

    `dialeto` é o dialeto do sqlglot ("postgres" | "mysql" | "tsql"): o SQL tem que SAIR na
    sintaxe do banco alvo, e no T-SQL não existe `LIMIT` — o sqlglot emite `TOP`. O parse
    e a emissão usam o mesmo dialeto de propósito: são a leitura e a escrita da mesma query.
    """
    arvore = cast(exp.Query, sqlglot.parse_one(sql, read=dialeto))
    limite = arvore.args.get("limit")
    if isinstance(limite, exp.Limit):
        valor = limite.expression
        if isinstance(valor, exp.Literal) and valor.is_int and int(valor.name) <= teto:
            return sql
    elif isinstance(limite, exp.Fetch):
        contagem = limite.args.get("count")
        if isinstance(contagem, exp.Literal) and contagem.is_int and int(contagem.name) <= teto:
            return sql
    return arvore.limit(teto).sql(dialect=dialeto)
