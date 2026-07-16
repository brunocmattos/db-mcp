import pytest

from db_mcp.errors import ForaDaAllowlist
from db_mcp.guardrails.policy import (
    checar_allowlist,
    injetar_limit,
    tabelas_referenciadas,
)


def test_extrai_tabelas():
    assert tabelas_referenciadas("SELECT * FROM public.clientes c JOIN pedidos e ON true") == {
        "public.clientes",
        "pedidos",
    }


def test_allowlist_estrela_permite_tudo():
    checar_allowlist("SELECT * FROM qualquer_tabela", ["*"])  # não levanta


def test_allowlist_bloqueia_fora_da_lista():
    with pytest.raises(ForaDaAllowlist):
        checar_allowlist("SELECT * FROM usuarios", ["public.clientes"])


def test_allowlist_aceita_nome_simples_ou_qualificado():
    checar_allowlist("SELECT * FROM clientes", ["clientes"])
    checar_allowlist("SELECT * FROM public.clientes", ["public.clientes"])


def test_allowlist_qualificada_nao_e_burlada_trocando_schema():
    # Furo: uma entrada qualificada (public.clientes) NÃO pode liberar outro schema
    # só porque o nome curto coincide.
    with pytest.raises(ForaDaAllowlist):
        checar_allowlist("SELECT * FROM secret.clientes", ["public.clientes"])
    with pytest.raises(ForaDaAllowlist):
        checar_allowlist("SELECT * FROM outro.usuarios", ["public.usuarios"])


def test_allowlist_nao_qualificada_libera_o_nome_em_qualquer_schema():
    # Entrada SEM schema é uma escolha explícita: aquele nome, em qualquer schema.
    checar_allowlist("SELECT * FROM public.clientes", ["clientes"])
    checar_allowlist("SELECT * FROM outro.clientes", ["clientes"])


def test_allowlist_qualificada_bloqueia_referencia_sem_schema():
    # Referência sem schema não casa com entrada qualificada: o search_path é ambíguo,
    # então negamos por segurança (o usuário deve qualificar ou liberar o nome curto).
    with pytest.raises(ForaDaAllowlist):
        checar_allowlist("SELECT * FROM clientes", ["public.clientes"])


def test_cte_nao_e_confundido_com_tabela():
    # O nome de um CTE (WITH) não é uma tabela real e não deve cair na allowlist.
    assert tabelas_referenciadas("WITH tmp AS (SELECT * FROM clientes) SELECT * FROM tmp") == {
        "clientes"
    }
    checar_allowlist("WITH tmp AS (SELECT * FROM clientes) SELECT * FROM tmp", ["clientes"])


def test_cte_em_subquery_nao_sombreia_tabela_real():
    # Furo de escopo: um CTE de mesmo nome definido DENTRO de uma subquery não pode
    # esconder a tabela real referenciada no FROM externo.
    sql = "SELECT * FROM secret WHERE 1 = (WITH secret AS (SELECT 1) SELECT 1)"
    assert "secret" in tabelas_referenciadas(sql)
    with pytest.raises(ForaDaAllowlist):
        checar_allowlist(sql, ["public.users"])


def test_cte_irmao_posterior_nao_sombreia_tabela_real():
    # WITH não-recursivo: 'a' (definido antes) não enxerga o CTE 'secret' (definido depois),
    # então FROM secret dentro de 'a' é a TABELA real — não pode furar a allowlist.
    sql = "WITH a AS (SELECT * FROM secret), secret AS (SELECT 1) SELECT * FROM a"
    assert "secret" in tabelas_referenciadas(sql)
    with pytest.raises(ForaDaAllowlist):
        checar_allowlist(sql, ["public.users"])


def test_cte_com_alias_nao_e_confundido_com_tabela():
    assert tabelas_referenciadas("WITH tmp AS (SELECT * FROM clientes) SELECT * FROM tmp t") == {
        "clientes"
    }


def test_limit_all_nao_gera_limit_duplicado():
    # Regressão: LIMIT ALL não pode virar "LIMIT ALL LIMIT 100" (SQL inválido).
    out = injetar_limit("SELECT * FROM t LIMIT ALL", 100)
    assert out.upper().count("LIMIT") == 1
    assert "LIMIT 100" in out.upper()


def test_fetch_first_gigante_e_reduzido_ao_teto():
    out = injetar_limit("SELECT * FROM t FETCH FIRST 999999 ROWS ONLY", 100)
    assert "999999" not in out
    assert "LIMIT 100" in out.upper()


def test_fetch_first_pequeno_e_respeitado():
    out = injetar_limit("SELECT * FROM t FETCH FIRST 3 ROWS ONLY", 100)
    assert out == "SELECT * FROM t FETCH FIRST 3 ROWS ONLY"


def test_injeta_limit_quando_ausente():
    assert injetar_limit("SELECT * FROM t", 100).rstrip().endswith("LIMIT 100")


def test_nao_duplica_limit_existente():
    sql = "SELECT * FROM t LIMIT 5"
    assert injetar_limit(sql, 100) == sql


def test_limit_gigante_do_cliente_e_reduzido_ao_teto():
    # Um LIMIT enorme não pode furar o teto (evita puxar milhões de linhas).
    out = injetar_limit("SELECT * FROM t LIMIT 999999999", 100)
    assert "999999999" not in out
    assert "LIMIT 100" in out.upper()


def test_limit_nao_literal_e_reduzido_ao_teto():
    out = injetar_limit("SELECT * FROM t LIMIT (SELECT 999999)", 100)
    assert "LIMIT 100" in out.upper()


def test_information_schema_sempre_liberado():
    # introspecção não pode ser bloqueada pela allowlist restrita
    checar_allowlist("SELECT * FROM information_schema.tables", ["clientes"])
