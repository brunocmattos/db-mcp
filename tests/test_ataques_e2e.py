"""Teste de FIACAO: os guardrails estao ligados no caminho real ate o banco?

Os unitarios (test_sql.py) provam que o validador esta CORRETO. Estes provam que
ele esta PLUGADO. Sao coisas diferentes: um validador perfeito que ninguem chama
nao protege ninguem.

Parametrizado por dialeto: as fases 1 e 2 so acrescentam a sua tabela.
"""

import os

import pytest

from db_mcp.config import Settings
from db_mcp.errors import ForaDaAllowlist, McpDbError, SomenteLeitura, SqlInvalido
from db_mcp.server import Nucleo

_TEM_BANCO = os.path.exists(".env") or bool(os.getenv("PG_HOST"))
pytestmark = pytest.mark.skipif(not _TEM_BANCO, reason="sem banco configurado")

ATAQUES_POSTGRES = [
    ("UPDATE clientes SET cidade='x'", SomenteLeitura),
    ("CREATE TABLE zz (n int)", SomenteLeitura),
    ("SELECT 1; DROP TABLE clientes", SqlInvalido),
    ("SELECT * INTO nova FROM clientes", SomenteLeitura),
    ("SELECT * FROM clientes FOR UPDATE", SomenteLeitura),
    ("WITH x AS (DELETE FROM clientes RETURNING *) SELECT * FROM x", SomenteLeitura),
    ("SELECT pg_read_file('/etc/passwd')", SomenteLeitura),
    ("SELECT \"pg_read_file\"('/etc/passwd')", SomenteLeitura),
    ("SELECT pg_catalog.pg_read_file('/etc/passwd')", SomenteLeitura),
    ("SELECT pg_sleep(30)", SomenteLeitura),
    ("SELECT set_config('statement_timeout','0',false)", SomenteLeitura),
    ("SELECT query_to_xml('SELECT * FROM clientes',true,true,'')", SomenteLeitura),
]


@pytest.fixture
def nucleo():
    n = Nucleo(Settings.load(env_file=None, yaml_file="config.example.yaml"))
    yield n
    n.db.close()


@pytest.mark.parametrize("sql,esperado", ATAQUES_POSTGRES)
def test_ataque_e_barrado_no_caminho_real(nucleo, sql, esperado):
    with pytest.raises(esperado):
        nucleo.consultar(sql)


def test_select_legitimo_atravessa_o_caminho_todo(nucleo):
    r = nucleo.consultar("SELECT 1 AS n")
    assert r["linhas"] == [{"n": 1}]
    assert r["truncado"] is False


def test_allowlist_esta_ligada_no_caminho_real(nucleo):
    # Nao basta checar_allowlist estar correta: ela tem que ser CHAMADA.
    nucleo.s.allowlist = ["clientes"]
    nucleo.consultar("SELECT * FROM clientes LIMIT 1")  # liberada: passa
    with pytest.raises(ForaDaAllowlist):
        nucleo.consultar("SELECT * FROM pedidos LIMIT 1")


def test_recusa_deixa_rastro_na_auditoria(nucleo, tmp_path):
    # A trilha de auditoria e o que sobra quando algo da errado: uma recusa que
    # nao e logada e uma recusa que ninguem descobre.
    nucleo.aud.caminho = str(tmp_path / "audit.log")
    with pytest.raises(McpDbError):
        nucleo.consultar("UPDATE clientes SET cidade='x'")
    conteudo = (tmp_path / "audit.log").read_text(encoding="utf-8")
    assert "somente_leitura" in conteudo
