import os

import pytest

from pg_readonly_mcp.config import Settings
from pg_readonly_mcp.db import Database
from pg_readonly_mcp.errors import ErroBanco
from pg_readonly_mcp.server import Nucleo

# Roda só quando há banco configurado: um .env na raiz OU PG_HOST no ambiente.
_TEM_BANCO = os.path.exists(".env") or bool(os.getenv("PG_HOST"))
pytestmark = pytest.mark.skipif(
    not _TEM_BANCO, reason="sem banco configurado (crie .env ou defina PG_HOST)"
)


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


def test_trunca_quando_passa_do_teto(db):
    linhas, truncado = db.executar("SELECT g FROM generate_series(1, 100) g", max_rows=5)
    assert len(linhas) == 5
    assert truncado is True


def test_truncado_pelo_caminho_completo_do_nucleo(monkeypatch):
    # Regressão do bug em que `truncado` era sempre False quando o LIMIT era auto-injetado.
    monkeypatch.setenv("MAX_ROWS", "5")
    s = Settings.load()
    nucleo = Nucleo(s)
    try:
        resp = nucleo.consultar("SELECT g FROM generate_series(1, 100) g")
        assert resp["total"] == 5
        assert resp["truncado"] is True
    finally:
        nucleo.db.close()
