"""Corpus de ataque do dialeto SQL Server (Fase 2 T2).

Arquivo separado de propósito, igual ao `test_sql_mysql.py`: o driver é um extra
OPCIONAL, e o `importorskip` abaixo faz o módulo inteiro se pular sem derrubar a
suíte de quem não instalou o extra.

Mesmo mecanismo (`validar`), lista diferente — a tese do projeto em forma de teste.
"""

import pytest

pytest.importorskip("pymssql", reason="extra `sqlserver` não instalado")

from db_mcp.dialetos import obter_dialeto
from db_mcp.dialetos.base import Perfil
from db_mcp.errors import McpDbError, SomenteLeitura
from db_mcp.guardrails.sql import validar

SS = obter_dialeto("sqlserver")


def _recusa(sql: str) -> None:
    with pytest.raises(McpDbError):
        validar(sql, SS, Perfil.SOMENTE_LEITURA)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM OPENQUERY(srv, 'SELECT 1')",
        "SELECT * FROM OPENDATASOURCE('SQLNCLI','x').db.dbo.t",
        "SELECT * FROM xp_cmdshell('dir')",
        "SELECT * FROM fn_get_audit_file('x', NULL, NULL)",
        "SELECT * FROM fn_trace_gettable('x', 1)",
    ],
)
def test_funcoes_perigosas_sao_recusadas_pela_blocklist(sql):
    # MEDIDO: estas chegam como exp.Anonymous e passam a checagem de raiz Select.
    # Quem barra é funcs_proibidas — o mecanismo já existe, a lista é do dialeto.
    with pytest.raises(SomenteLeitura, match="função não permitida"):
        validar(sql, SS, Perfil.SOMENTE_LEITURA)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT [xp_cmdshell]('dir')",
        "SELECT \"xp_cmdshell\"('dir')",
    ],
)
def test_citacao_nao_escapa_da_blocklist(sql):
    # 🪤 No T-SQL aspas duplas são CITAÇÃO de identificador — o OPOSTO do MySQL, onde
    # são STRING. O caso do Postgres porta pra cá; o do MySQL NÃO. `.name` normaliza.
    with pytest.raises(SomenteLeitura, match="função não permitida"):
        validar(sql, SS, Perfil.SOMENTE_LEITURA)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM OPENROWSET('SQLNCLI', 'srv';'u';'p', 'SELECT 1')",
        "SELECT * FROM OPENROWSET(BULK 'C:\\x.txt', SINGLE_CLOB) AS a",
        "WAITFOR DELAY '00:00:10'",
        "EXECUTE AS LOGIN = 'sa'",
        "SELECT 1\nGO\nDROP TABLE t",
    ],
)
def test_recusados_hoje_apenas_por_parseerror(sql):
    # ⚠️ REGRESSÃO DELIBERADA. Estes falham FECHADO por ACIDENTE: o sqlglot não os
    # parseia, então morrem em SqlInvalido. Se uma versão nova passar a parseá-los, eles
    # viram Select com raiz válida e escapam. O teste exige RECUSA (McpDbError), NÃO o
    # mecanismo — assim ele AVISA em vez de o buraco abrir calado. Mesmo padrão do
    # INTO OUTFILE no MySQL (test_sql_mysql.py).
    _recusa(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO t VALUES (1)",
        "SELECT * INTO nova FROM t",
        "EXEC sp_who",
        "EXEC xp_cmdshell 'dir'",
        "EXEC sp_executesql N'SELECT 1'",
    ],
)
def test_escrita_e_execucao_sao_recusadas(sql):
    _recusa(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT TOP 10 * FROM t",
        "WITH c AS (SELECT 1 AS x) SELECT * FROM c",
        "SELECT 1 UNION SELECT 2",
        "SELECT * FROM t FOR XML AUTO",
    ],
)
def test_select_legitimo_passa(sql):
    validar(sql, SS, Perfil.SOMENTE_LEITURA)  # não levanta


def test_lista_e_do_dialeto_nao_global():
    fp = SS.funcs_proibidas
    assert "openquery" in fp
    assert "xp_cmdshell" in fp
    assert "load_file" not in fp  # MySQL
    assert "pg_read_file" not in fp  # Postgres
