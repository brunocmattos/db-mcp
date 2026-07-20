import pytest
import sqlglot

from db_mcp.dialetos import DIALETOS_IMPLEMENTADOS, obter_dialeto
from db_mcp.dialetos.base import Perfil


def test_obter_dialeto_postgres():
    d = obter_dialeto("postgres")
    assert d.nome == "postgres"
    assert d.sqlglot_dialeto == "postgres"
    assert d.schema_padrao == "public"


def test_dialeto_desconhecido_falha_com_erro_legivel():
    with pytest.raises(ValueError, match="dialeto desconhecido"):
        obter_dialeto("oracle")


def test_postgres_traz_as_funcoes_proibidas_do_banco():
    fp = obter_dialeto("postgres").funcs_proibidas
    assert "pg_read_file" in fp
    assert "query_to_xml" in fp
    assert "set_config" in fp
    # a lista é do dialeto, não global: função de OUTRO banco não entra aqui
    assert "load_file" not in fp  # MySQL
    assert "openquery" not in fp  # T-SQL


def test_sql_amostra_do_postgres_usa_limit_e_cita_o_nome():
    # identify=True cita o identificador ("clientes"): é o que faz o nome reservado
    # (Order -> [Order] no T-SQL) funcionar sem regex. No postgres sai com aspas duplas.
    sql = obter_dialeto("postgres").sql_amostra("clientes", 5)
    assert sql == 'SELECT * FROM "clientes" LIMIT 5'


def test_perfil_so_tem_somente_leitura_nesta_fase():
    # A escrita ganha spec próprio. O parâmetro existe pra costura ficar no lugar
    # certo, mas nesta fase só há um valor possível.
    assert [p.name for p in Perfil] == ["SOMENTE_LEITURA"]


@pytest.mark.parametrize("nome", DIALETOS_IMPLEMENTADOS)
def test_invariante_todo_dialeto(nome):
    # Gate pra TODO dialeto futuro (Fases 1 e 2), não só o postgres. Enumerado a partir
    # do _REGISTRO (fonte única): quem acrescentar um dialeto sem satisfazer isto quebra
    # o CI, não uma query em produção. Cobre os dois traps documentados no CLAUDE.md:
    d = obter_dialeto(nome)
    # (a) sqlglot_dialeto tem que ser um nome que o sqlglot CONHECE — pega o clássico
    #     "sqlserver" (ValueError: Unknown dialect) escrito no lugar de "tsql".
    assert sqlglot.transpile("SELECT 1", read=d.sqlglot_dialeto, write=d.sqlglot_dialeto) == [
        "SELECT 1"
    ]
    # (b) funcs_proibidas NÃO pode ser vazia — é o único ponto da costura que falharia
    #     ABERTO: um stub com a lista por preencher liberaria load_file('/etc/passwd').
    assert d.funcs_proibidas, f"{nome}: funcs_proibidas vazia falharia ABERTA"
