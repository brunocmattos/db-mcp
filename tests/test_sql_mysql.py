"""Corpus de ataque do dialeto MySQL (Fase 1 T6).

Arquivo separado do `test_sql.py` de propósito: o driver do MySQL é um extra
OPCIONAL, e o `importorskip` abaixo faz este módulo inteiro se pular sem derrubar
os testes do Postgres de quem não instalou o extra.

O par de `test_sql.py` — mesmo mecanismo (`validar`), lista diferente. É a tese do
projeto em forma de teste: **muda a LISTA, não o mecanismo.**
"""

import pytest

pytest.importorskip("mysql.connector", reason="extra `mysql` não instalado")

from db_mcp.dialetos import obter_dialeto
from db_mcp.dialetos.base import Perfil
from db_mcp.errors import McpDbError, SomenteLeitura, SqlInvalido
from db_mcp.guardrails.sql import validar

MY = obter_dialeto("mysql")


def _validar_my(sql: str) -> None:
    validar(sql, MY, Perfil.SOMENTE_LEITURA)


@pytest.mark.parametrize(
    "sql",
    [
        "select 1",
        "SELECT id, nome FROM clientes WHERE id = 10",
        "SELECT `nome` FROM `clientes`",  # crases: a citação do MySQL
        "WITH t AS (SELECT * FROM pedidos) SELECT count(*) FROM t",
        "select a from tab union select b from outra",
        "SELECT * FROM t LIMIT 10",
    ],
)
def test_select_valido_passa(sql):
    _validar_my(sql)  # não levanta


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
        "REPLACE INTO clientes (nome) VALUES ('x')",  # só-MySQL: DELETE+INSERT disfarçado
        "RENAME TABLE clientes TO outros",
    ],
)
def test_escrita_e_ddl_sao_bloqueados(sql):
    with pytest.raises((SomenteLeitura, SqlInvalido)):
        _validar_my(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT load_file('/etc/passwd')",  # lê arquivo do servidor
        "SELECT `load_file`('/etc/passwd')",  # citado não escapa a blocklist
        "SELECT `get_lock`('trava', 10)",
        "SELECT mysql.`sleep`(10)",  # qualificado + citado
        "SELECT sleep(10)",  # DoS: segura a conexão do pool
        "SELECT benchmark(100000000, md5('x'))",  # DoS por CPU
        "SELECT get_lock('trava', 10)",  # lock nomeado que VAZA no pool
        "SELECT release_lock('trava')",
        "SELECT is_free_lock('trava')",
        "SELECT is_used_lock('trava')",
        "SELECT master_pos_wait('log', 1)",  # bloqueia esperando replicação
        "SELECT source_pos_wait('log', 1)",
        "SELECT sys_exec('rm -rf /')",  # UDF do lib_mysqludf_sys
        "SELECT sys_eval('id')",
        "select 1; select 2",  # múltiplas (mesmo ambas SELECT)
        "SELECT 1; DROP TABLE clientes",
        "SELECT * FROM clientes FOR UPDATE",  # lock de escrita
        "SELECT * FROM clientes FOR SHARE",
        "SELECT * FROM clientes LOCK IN SHARE MODE",  # forma antiga do MySQL
        "SELECT * INTO nova FROM clientes",  # SELECT INTO
    ],
)
def test_casos_adversariais_bloqueados(sql):
    with pytest.raises((SomenteLeitura, SqlInvalido)):
        _validar_my(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM clientes INTO OUTFILE '/tmp/vaza.txt'",
        "SELECT * FROM clientes INTO DUMPFILE '/tmp/vaza.bin'",
        "SELECT nome FROM clientes INTO OUTFILE '/var/www/html/x.php'",
        # variações com opções, pra não depender de UMA forma sintática
        "SELECT * FROM clientes INTO OUTFILE '/tmp/x' FIELDS TERMINATED BY ','",
    ],
)
def test_into_outfile_e_dumpfile_recusados(sql):
    """🚨 REGRESSÃO DELIBERADA — o exfiltrador nº 1 do MySQL.

    `INTO OUTFILE` escreve arquivo no servidor: com FILE concedido, vira `.php` no
    docroot. Hoje ele é barrado porque o sqlglot dá ParseError — ou seja, **falha
    fechado por acidente, não por desenho**. Se um upgrade do sqlglot passar a
    parseá-lo, o SQL vira um `Select` comum e atravessaria o validador em silêncio.

    Por isso o teste exige apenas **recusa** (`McpDbError`, a família toda), e não um
    tipo específico: o dia em que o mecanismo mudar, o teste continua exigindo a
    recusa e quem quebrou tem que acrescentar a defesa de verdade — em vez de o
    buraco abrir sem ninguém notar.
    """
    with pytest.raises(McpDbError):
        _validar_my(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM t;",  # ponto-e-vírgula final é ok
        "SELECT 1 -- comentario com ; DROP TABLE t",
        "SELECT 1 # comentario de hash, que so' o MySQL tem",
        "SELECT nome FROM usuarios WHERE nome = 'a;b'",  # ; DENTRO de string
    ],
)
def test_casos_seguros_passam(sql):
    _validar_my(sql)  # não levanta


def test_a_citacao_do_mysql_e_a_crase_nao_a_aspa_dupla():
    """MEDIDO — a diferença que quase me fez escrever um teste falso.

    No Postgres, `"pg_read_file"(...)` é a MESMA função entre aspas, e o corpus testa
    justamente que citar não escapa da blocklist. No MySQL, aspas duplas são **string
    literal** (sem ANSI_QUOTES): `"load_file"('/x')` não é função citada, é uma string
    seguida de parênteses — ou seja, erro de sintaxe. Copiar o caso do Postgres pra cá
    testaria uma coisa que não existe.

    As duas formas são recusadas, mas por mecanismos DIFERENTES, e a distinção importa:
    só a crase prova que a blocklist está fazendo o trabalho.
    """
    # crase = citação de verdade -> chega na blocklist
    with pytest.raises(SomenteLeitura):
        _validar_my("SELECT `load_file`('/etc/passwd')")
    # aspas duplas = string -> morre no parser (recusado, mas por acidente sintático)
    with pytest.raises(SqlInvalido):
        _validar_my("SELECT \"load_file\"('/etc/passwd')")


def test_a_lista_e_do_dialeto_nao_global():
    """O mecanismo é compartilhado, a lista não: função de OUTRO banco não entra aqui."""
    fp = MY.funcs_proibidas
    assert "load_file" in fp and "get_lock" in fp
    assert "pg_read_file" not in fp  # Postgres
    assert "openquery" not in fp  # T-SQL (Fase 2)


def test_funcao_perigosa_do_postgres_nao_e_barrada_no_mysql():
    """Prova que a separação é real: `pg_sleep` não existe no MySQL, então o validador
    do MySQL o trata como função qualquer. Se este teste começar a falhar, alguém
    voltou a ter uma blocklist global — o que faria a lista de um banco mascarar a
    ausência da lista de outro."""
    _validar_my("SELECT pg_sleep(10)")  # não levanta: não é função do MySQL


def test_sql_amostra_do_mysql_usa_crases():
    # A crase é a ASSINATURA de fiação: se sair com aspas duplas, o servidor está
    # montando o SQL pelo dialeto errado.
    assert MY.sql_amostra("clientes", 5) == "SELECT * FROM `clientes` LIMIT 5"


def test_sql_amostra_recusa_nome_que_nao_e_tabela():
    for nome in ("clientes; DROP TABLE x", "(SELECT 1)", "clientes WHERE 1=1"):
        with pytest.raises(SqlInvalido):
            MY.sql_amostra(nome, 5)
