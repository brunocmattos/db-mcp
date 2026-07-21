import os

import pytest

from db_mcp.config import Settings
from db_mcp.db import Database
from db_mcp.errors import ErroBanco
from db_mcp.server import Nucleo

# Roda só quando há banco configurado: um .env na raiz OU DB_HOST no ambiente.
_TEM_BANCO = os.path.exists(".env") or bool(os.getenv("DB_HOST"))
pytestmark = pytest.mark.skipif(
    not _TEM_BANCO, reason="sem banco configurado (crie .env ou defina DB_HOST)"
)


def _so_no_dialeto(esperado: str) -> None:
    """Pula o teste se a suíte não estiver rodando contra o dialeto `esperado`.

    A maior parte dos testes é portável (a tese do projeto). Alguns não são — reset de
    sessão e funções de sistema mudam por banco —, e esses precisam do PAR: um por
    dialeto, não um do Postgres pulado em silêncio no MySQL.
    """
    atual = Settings.load().dialeto
    if atual != esperado:
        pytest.skip(f"específico do {esperado}; a suíte está rodando contra {atual}")


@pytest.fixture
def db():
    s = Settings.load()
    d = Database(s)
    yield d
    d.close()


def test_le_uma_linha(db):
    linhas, truncado = db.executar("SELECT 1 AS um", max_rows=10)
    assert linhas == [{"um": 1}]
    assert truncado is False


def test_conexao_e_read_only(db):
    # O banco recusa a escrita; o db.py embrulha o erro do psycopg em ErroBanco.
    with pytest.raises(ErroBanco):
        db.executar("CREATE TABLE zzz_mcp(i int)", max_rows=10)


def test_tabela_inexistente_vira_erro_banco(db):
    with pytest.raises(ErroBanco):
        db.executar("SELECT * FROM tabela_que_nao_existe_zzz", max_rows=10)


def test_query_repetida_nao_quebra_por_prepared_statement(monkeypatch):
    # Regressão: com o reset (DISCARD ALL), a MESMA query repetida cruzava o
    # prepare_threshold do psycopg e quebrava. Deve rodar N vezes sem erro.
    monkeypatch.setenv("POOL_MIN", "1")
    monkeypatch.setenv("POOL_MAX", "1")
    s = Settings.load()
    d = Database(s)
    try:
        for _ in range(12):  # > prepare_threshold padrão (5)
            linhas, _ = d.executar("SELECT 1 AS um", max_rows=10)
            assert linhas == [{"um": 1}]
    finally:
        d.close()


def test_pool_reseta_estado_de_sessao_entre_clientes(monkeypatch):
    # Com uma única conexão no pool, um GUC mudado numa consulta NÃO pode vazar para a
    # próxima que reusa a mesma conexão física (o reset faz DISCARD ALL).
    _so_no_dialeto("postgres")
    monkeypatch.setenv("POOL_MIN", "1")
    monkeypatch.setenv("POOL_MAX", "1")
    s = Settings.load()
    d = Database(s)
    try:
        d.executar("SELECT set_config('search_path', 'pg_temp', false)", max_rows=1)
        linhas, _ = d.executar("SELECT current_setting('search_path') AS sp", max_rows=1)
        assert "pg_temp" not in linhas[0]["sp"]
    finally:
        d.close()


def test_mysql_reaplica_read_only_a_cada_checkout(monkeypatch):
    """🚨 O par MySQL do teste acima — e o cadeado que FALHA ABERTA.

    MEDIDO (mysql-connector 9.7 / MySQL 8.4): `pool_reset_session=True` ZERA o
    `SET SESSION TRANSACTION READ ONLY` quando a conexão volta ao pool (mesmo
    CONNECTION_ID, 1 → 0), e zera o `max_execution_time` junto.

    Ou seja: aplicar esses dois uma vez só, na criação do pool, deixaria as conexões
    GRAVÁVEIS e SEM TIMEOUT a partir do 2º checkout — em silêncio, sem erro nenhum.
    Diferente do Postgres, onde `default_transaction_read_only` no role faz o servidor
    garantir sozinho, aqui o cinto é da aplicação. Este teste é o que impede alguém de
    "simplificar" o `_PoolMySQL.connection()` movendo o SET pra fora do checkout.
    """
    _so_no_dialeto("mysql")
    monkeypatch.setenv("POOL_MIN", "1")
    monkeypatch.setenv("POOL_MAX", "1")
    s = Settings.load()
    d = Database(s)
    try:
        sql = "SELECT @@session.transaction_read_only AS ro, @@session.max_execution_time AS met"
        for i in range(3):  # 3 checkouts na MESMA conexão física (pool_max=1)
            linhas, _ = d.executar(sql, max_rows=1)
            assert linhas[0]["ro"] == 1, f"checkout {i + 1}: conexão voltou GRAVÁVEL"
            assert linhas[0]["met"] == s.statement_timeout_ms, f"checkout {i + 1}: sem timeout"
    finally:
        d.close()


def test_trunca_quando_passa_do_teto(db):
    # `pedidos` tem 10 linhas nos DOIS demos; o generate_series de antes era Postgres-only
    linhas, truncado = db.executar("SELECT id FROM pedidos", max_rows=5)
    assert len(linhas) == 5
    assert truncado is True


def test_truncado_pelo_caminho_completo_do_nucleo(monkeypatch):
    # Regressão do bug em que `truncado` era sempre False quando o LIMIT era auto-injetado.
    monkeypatch.setenv("MAX_ROWS", "5")
    s = Settings.load()
    nucleo = Nucleo(s)
    try:
        resp = nucleo.consultar("SELECT id FROM pedidos")
        assert resp["total"] == 5
        assert resp["truncado"] is True
    finally:
        nucleo.db.close()
