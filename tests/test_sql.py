import pytest

from db_mcp.dialetos import obter_dialeto
from db_mcp.dialetos.base import Perfil
from db_mcp.errors import SomenteLeitura, SqlInvalido
from db_mcp.guardrails.sql import validar

PG = obter_dialeto("postgres")


def _validar_pg(sql: str) -> None:
    validar(sql, PG, Perfil.SOMENTE_LEITURA)


@pytest.mark.parametrize(
    "sql",
    [
        "select 1",
        "SELECT id, nome FROM public.clientes WHERE id = 10",
        "WITH t AS (SELECT * FROM pedidos) SELECT count(*) FROM t",
        "select a from tab union select b from outra",
        "SELECT a FROM t INTERSECT SELECT a FROM u",  # operação de conjunto só-leitura
        "SELECT a FROM t EXCEPT SELECT a FROM u",
    ],
)
def test_select_valido_passa(sql):
    _validar_pg(sql)  # não levanta


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO clientes (nome) VALUES ('x')",
        "UPDATE clientes SET nome='x'",
        "DELETE FROM clientes",
        "DROP TABLE clientes",
        "TRUNCATE clientes",
        "CREATE TABLE t(i int)",
        "ALTER TABLE clientes ADD COLUMN x int",
        "GRANT SELECT ON clientes TO x",
    ],
)
def test_escrita_e_ddl_sao_bloqueados(sql):
    with pytest.raises(SomenteLeitura):
        _validar_pg(sql)


def test_cte_que_escreve_e_bloqueada():
    sql = "WITH x AS (INSERT INTO t VALUES (1) RETURNING *) SELECT * FROM x"
    with pytest.raises(SomenteLeitura):
        _validar_pg(sql)


def test_multiplas_instrucoes_bloqueadas():
    with pytest.raises(SqlInvalido):
        _validar_pg("SELECT 1; DROP TABLE t")


def test_funcao_perigosa_bloqueada():
    with pytest.raises(SomenteLeitura):
        _validar_pg("SELECT pg_read_file('/etc/passwd')")


def test_sql_quebrado_e_invalido():
    with pytest.raises(SqlInvalido):
        _validar_pg("SELECT FROM WHERE")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM t WHERE x = 'aberta",  # aspa simples nunca fechada
        'SELECT " FROM t',  # aspa dupla nunca fechada
        "SELECT * FROM t WHERE x = 'a' || 'b",  # aspa aberta depois de string válida
    ],
)
def test_sql_malformado_vira_recusa_tratada(sql):
    # Regressão: quando o TOKENIZER morre antes do parser, o sqlglot levanta TokenError —
    # que NÃO é subclasse de ParseError (são irmãs sob SqlglotError). Com `except ParseError`
    # isto vazava cru: não virava SqlInvalido, escapava do `except McpDbError` do server.py
    # e a recusa saía SEM auditoria. Falhava fechado (a query não chegava no banco), mas
    # sem rastro — e o rastro é o que mais importa na trilha.
    with pytest.raises(SqlInvalido):
        _validar_pg(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT pg_sleep(10)",  # função de DoS
        "COPY clientes TO '/tmp/x'",  # COPY (exfiltração/escrita)
        "SELECT lo_export(1, '/tmp/x')",  # escrita de arquivo em disco
        "select 1; select 2",  # múltiplas (mesmo ambas SELECT)
        "SELECT * INTO nova FROM clientes",  # SELECT INTO cria tabela
        "SELECT nextval('minha_seq')",  # avança a sequence (efeito colateral)
        "SELECT setval('minha_seq', 1)",  # altera a sequence
        "SELECT * FROM clientes FOR UPDATE",  # lock de escrita
        "SELECT * FROM clientes FOR SHARE",  # lock
        "SELECT \"pg_read_file\"('/etc/passwd')",  # nome entre aspas não escapa a blocklist
        "SELECT \"dblink\"('host=x', 'UPDATE t SET x=1')",  # dblink abriria conexão de escrita
        "SELECT \"nextval\"('s')",  # aspas em função de efeito colateral
        'SELECT pg_catalog."pg_sleep"(10)',  # qualificado + aspas
        "SELECT set_config('statement_timeout', '0', false)",  # muda GUC de sessão
        "SELECT pg_advisory_lock(1)",  # advisory lock (efeito colateral que vaza no pool)
        "SELECT pg_advisory_xact_lock(1)",
        "SELECT pg_sleep_for('5 minutes')",  # alias de pg_sleep (DoS)
        "SELECT pg_sleep_until(now())",
        "SELECT query_to_xml('SELECT * FROM secret', true, false, '')",  # fura a allowlist
        "SELECT table_to_xml('secret', true, false, '')",
        "SELECT pg_logical_emit_message(true, 'p', 'x')",  # escreve WAL durável em read-only
        "SELECT pg_notify('c', 'x')",  # NOTIFY assíncrono
        "SELECT txid_current()",  # consome um XID
        "SELECT lo_get(1)",  # lê large object fora da allowlist
    ],
)
def test_casos_adversariais_bloqueados(sql):
    with pytest.raises((SomenteLeitura, SqlInvalido)):
        _validar_pg(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM t;",  # ponto-e-vírgula final é ok
        "SELECT 1 -- comentario com ; DROP TABLE t",  # comentário não conta como comando
        "SELECT nome FROM usuarios WHERE nome = 'a;b'",  # ; DENTRO de string não é separador
    ],
)
def test_casos_seguros_passam(sql):
    _validar_pg(sql)  # não levanta
