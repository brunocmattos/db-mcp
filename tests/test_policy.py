import pytest

from db_mcp.dialetos import obter_dialeto
from db_mcp.errors import ForaDaAllowlist
from db_mcp.guardrails.policy import (
    checar_allowlist,
    injetar_limit,
    tabelas_referenciadas,
)

# O dialeto real, não a string crua: se o `sqlglot_dialeto` do Postgres mudar, estes
# testes acompanham em vez de continuarem verdes testando outra coisa (padrão da T6).
PG = obter_dialeto("postgres").sqlglot_dialeto


def test_extrai_tabelas():
    assert tabelas_referenciadas("SELECT * FROM public.clientes c JOIN pedidos e ON true", PG) == {
        "public.clientes",
        "pedidos",
    }


def test_allowlist_estrela_permite_tudo():
    checar_allowlist("SELECT * FROM qualquer_tabela", ["*"], PG)  # não levanta


def test_allowlist_bloqueia_fora_da_lista():
    with pytest.raises(ForaDaAllowlist):
        checar_allowlist("SELECT * FROM usuarios", ["public.clientes"], PG)


def test_allowlist_aceita_nome_simples_ou_qualificado():
    checar_allowlist("SELECT * FROM clientes", ["clientes"], PG)
    checar_allowlist("SELECT * FROM public.clientes", ["public.clientes"], PG)


def test_allowlist_qualificada_nao_e_burlada_trocando_schema():
    # Furo: uma entrada qualificada (public.clientes) NÃO pode liberar outro schema
    # só porque o nome curto coincide.
    with pytest.raises(ForaDaAllowlist):
        checar_allowlist("SELECT * FROM secret.clientes", ["public.clientes"], PG)
    with pytest.raises(ForaDaAllowlist):
        checar_allowlist("SELECT * FROM outro.usuarios", ["public.usuarios"], PG)


def test_allowlist_nao_qualificada_libera_o_nome_em_qualquer_schema():
    # Entrada SEM schema é uma escolha explícita: aquele nome, em qualquer schema.
    checar_allowlist("SELECT * FROM public.clientes", ["clientes"], PG)
    checar_allowlist("SELECT * FROM outro.clientes", ["clientes"], PG)


def test_allowlist_qualificada_bloqueia_referencia_sem_schema():
    # Referência sem schema não casa com entrada qualificada: o search_path é ambíguo,
    # então negamos por segurança (o usuário deve qualificar ou liberar o nome curto).
    with pytest.raises(ForaDaAllowlist):
        checar_allowlist("SELECT * FROM clientes", ["public.clientes"], PG)


def test_cte_nao_e_confundido_com_tabela():
    # O nome de um CTE (WITH) não é uma tabela real e não deve cair na allowlist.
    assert tabelas_referenciadas("WITH tmp AS (SELECT * FROM clientes) SELECT * FROM tmp", PG) == {
        "clientes"
    }
    checar_allowlist("WITH tmp AS (SELECT * FROM clientes) SELECT * FROM tmp", ["clientes"], PG)


def test_cte_em_subquery_nao_sombreia_tabela_real():
    # Furo de escopo: um CTE de mesmo nome definido DENTRO de uma subquery não pode
    # esconder a tabela real referenciada no FROM externo.
    sql = "SELECT * FROM secret WHERE 1 = (WITH secret AS (SELECT 1) SELECT 1)"
    assert "secret" in tabelas_referenciadas(sql, PG)
    with pytest.raises(ForaDaAllowlist):
        checar_allowlist(sql, ["public.users"], PG)


def test_cte_irmao_posterior_nao_sombreia_tabela_real():
    # WITH não-recursivo: 'a' (definido antes) não enxerga o CTE 'secret' (definido depois),
    # então FROM secret dentro de 'a' é a TABELA real — não pode furar a allowlist.
    sql = "WITH a AS (SELECT * FROM secret), secret AS (SELECT 1) SELECT * FROM a"
    assert "secret" in tabelas_referenciadas(sql, PG)
    with pytest.raises(ForaDaAllowlist):
        checar_allowlist(sql, ["public.users"], PG)


def test_cte_com_alias_nao_e_confundido_com_tabela():
    assert tabelas_referenciadas(
        "WITH tmp AS (SELECT * FROM clientes) SELECT * FROM tmp t", PG
    ) == {"clientes"}


def test_limit_all_nao_gera_limit_duplicado():
    # Regressão: LIMIT ALL não pode virar "LIMIT ALL LIMIT 100" (SQL inválido).
    out = injetar_limit("SELECT * FROM t LIMIT ALL", 100, PG)
    assert out.upper().count("LIMIT") == 1
    assert "LIMIT 100" in out.upper()


def test_fetch_first_gigante_e_reduzido_ao_teto():
    out = injetar_limit("SELECT * FROM t FETCH FIRST 999999 ROWS ONLY", 100, PG)
    assert "999999" not in out
    assert "LIMIT 100" in out.upper()


def test_fetch_first_pequeno_e_respeitado():
    out = injetar_limit("SELECT * FROM t FETCH FIRST 3 ROWS ONLY", 100, PG)
    assert out == "SELECT * FROM t FETCH FIRST 3 ROWS ONLY"


def test_injeta_limit_quando_ausente():
    assert injetar_limit("SELECT * FROM t", 100, PG).rstrip().endswith("LIMIT 100")


def test_nao_duplica_limit_existente():
    sql = "SELECT * FROM t LIMIT 5"
    assert injetar_limit(sql, 100, PG) == sql


def test_limit_gigante_do_cliente_e_reduzido_ao_teto():
    # Um LIMIT enorme não pode furar o teto (evita puxar milhões de linhas).
    out = injetar_limit("SELECT * FROM t LIMIT 999999999", 100, PG)
    assert "999999999" not in out
    assert "LIMIT 100" in out.upper()


def test_limit_nao_literal_e_reduzido_ao_teto():
    out = injetar_limit("SELECT * FROM t LIMIT (SELECT 999999)", 100, PG)
    assert "LIMIT 100" in out.upper()


def test_information_schema_sempre_liberado():
    # introspecção não pode ser bloqueada pela allowlist restrita
    checar_allowlist("SELECT * FROM information_schema.tables", ["clientes"], PG)


# --- Defeito 5.1: o SQL tem que SAIR na sintaxe do banco alvo ---------------------
# Testável já na Fase 0 porque o sqlglot suporta tsql/mysql nativamente — não depende
# dos nossos módulos de dialeto, que só existirão nas Fases 1 e 2.


def test_injetar_limit_tsql_sem_limite_usa_top():
    # A forma REAL do defeito 5.1 (medida): uma query T-SQL válida sem limite também
    # parseia em postgres, então o `dialect="postgres"` cravado emitia
    # "SELECT * FROM t LIMIT 100" — e LIMIT não existe no SQL Server. Era este o
    # caminho que produzia SQL inválido sem ninguém perceber.
    out = injetar_limit("SELECT * FROM t", 100, "tsql")
    assert "TOP 100" in out.upper()
    assert "LIMIT" not in out.upper()


def test_injetar_limit_tsql_reduz_top_acima_do_teto():
    # O teto vale no dialeto alvo: TOP acima do teto é normalizado pra TOP <teto>,
    # não pra LIMIT. (Com o parse cravado em postgres esta entrada nem chegava aqui:
    # morria antes, no ParseError — falha fechada, mas por acidente.)
    out = injetar_limit("SELECT TOP 9999 * FROM t", 100, "tsql")
    assert "TOP 100" in out.upper()
    assert "LIMIT" not in out.upper()
    assert "9999" not in out


def test_injetar_limit_tsql_respeita_top_dentro_do_teto():
    # Mesma decisão do Postgres: limite literal dentro do teto passa intocado.
    sql = "SELECT TOP 5 * FROM t"
    assert injetar_limit(sql, 100, "tsql") == sql


def test_injetar_limit_no_mysql_usa_limit():
    out = injetar_limit("SELECT * FROM t", 100, "mysql")
    assert "LIMIT 100" in out.upper()


def test_tabelas_referenciadas_le_no_dialeto_alvo():
    # A allowlist é o cadeado nº 3(b): ler no dialeto errado é ler outra query.
    # Backtick é MySQL — em postgres isto é ParseError, não uma tabela chamada `t`.
    assert tabelas_referenciadas("SELECT * FROM `pedidos`", "mysql") == {"pedidos"}
