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


def test_injetar_limit_tsql_converte_limit_para_top_mesmo_dentro_do_teto():
    # Regressão MEDIDA contra SQL Server real (T6): o sqlglot faz parse leniente de
    # `LIMIT n` mesmo com read="tsql", então uma query com LIMIT (sintaxe alheia ao
    # T-SQL) e valor dentro do teto batia no fast-path e saía intocada — o pymssql
    # recusava com "Incorrect syntax near '1'" porque LIMIT não existe no SQL Server.
    out = injetar_limit("SELECT * FROM clientes LIMIT 1", 100, "tsql")
    assert "TOP 1" in out.upper()
    assert "LIMIT" not in out.upper()


def test_injetar_limit_no_mysql_usa_limit():
    out = injetar_limit("SELECT * FROM t", 100, "mysql")
    assert "LIMIT 100" in out.upper()


def test_tabelas_referenciadas_le_no_dialeto_alvo():
    # A allowlist é o cadeado nº 3(b): ler no dialeto errado é ler outra query.
    # Backtick é MySQL — em postgres isto é ParseError, não uma tabela chamada `t`.
    assert tabelas_referenciadas("SELECT * FROM `pedidos`", "mysql") == {"pedidos"}


# --- Cross-database: o db-mcp fala com UM banco ------------------------------------
# MEDIDO em 2026-07-21: `tabelas_referenciadas` montava o nome com `t.db` + `t.name` e
# DESCARTAVA o `t.catalog`. `outrodb.public.clientes` era vista como `public.clientes` e
# casava com a entrada da allowlist feita para o banco CORRENTE — o cadeado nº 3 liberava
# um banco que ninguém liberou.
#
# Era latente, não explorável, e é por isso que passou: medido contra os bancos vivos, o
# Postgres recusa ("cross-database references are not implemented") e o MySQL dá erro de
# sintaxe (1064) — o cadeado nº 1 segurava. Mas o **SQL Server EXECUTA** nome de 3 partes,
# e um login costuma enxergar vários bancos da mesma instância; nome de 4 partes sai da
# instância inteira via linked server. A Fase 2 abriria o buraco no dia em que existisse.
#
# A regra: qualquer referência que carregue catalog é RECUSADA. Não é "compare com o banco
# configurado" — é um invariante do produto, o que o torna auditável sem olhar a config.


def test_allowlist_recusa_catalog_com_entrada_qualificada():
    with pytest.raises(ForaDaAllowlist):
        checar_allowlist("SELECT * FROM outrodb.public.clientes", ["public.clientes"], PG)


def test_allowlist_recusa_catalog_com_entrada_nao_qualificada():
    # O pior caso, e o mais comum: uma entrada curta libera aquele nome em qualquer
    # SCHEMA — nunca em outro BANCO. Sem esta, incluir o catalog no nome não resolveria
    # nada, porque `_tabela_permitida` casa pelo ÚLTIMO segmento.
    with pytest.raises(ForaDaAllowlist):
        checar_allowlist("SELECT * FROM outrodb.public.clientes", ["clientes"], PG)


def test_allowlist_recusa_linked_server_de_quatro_partes():
    # servidor.banco.schema.tabela: sai da instância inteira.
    with pytest.raises(ForaDaAllowlist):
        checar_allowlist("SELECT * FROM srv.folha.dbo.clientes", ["clientes"], "tsql")


def test_catalog_e_recusado_mesmo_com_allowlist_estrela():
    # `*` desliga a allowlist, não o invariante do produto: "um servidor, um banco".
    # Se `*` liberasse cross-database, a proteção sumiria justamente na config mais
    # usada — falha ABERTA no default.
    with pytest.raises(ForaDaAllowlist):
        checar_allowlist("SELECT * FROM outrodb.public.clientes", ["*"], PG)


def test_catalog_do_proprio_banco_tambem_e_recusado():
    # Consequência assumida da regra simples: `demo.public.clientes` é SQL válido no
    # Postgres quando `demo` é o banco corrente, e passa a ser recusado. A alternativa
    # (comparar com o db_dbname) exigiria a config aqui dentro, ampliando a superfície
    # de um cadeado de segurança. Quem precisa disto escreve o nome com 2 partes.
    with pytest.raises(ForaDaAllowlist):
        checar_allowlist("SELECT * FROM demo.public.clientes", ["public.clientes"], PG)


def test_tabelas_referenciadas_preserva_o_catalog():
    # A causa-raiz, testada direto: o nome extraído tem que CARREGAR o catalog, senão
    # a informação já se perdeu antes de a allowlist decidir.
    assert tabelas_referenciadas("SELECT * FROM outrodb.public.clientes", PG) == {
        "outrodb.public.clientes"
    }
