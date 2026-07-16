import json
import os

import pytest
from fastmcp import Client

from db_mcp.cli import montar

# E2E de verdade: sobe o servidor MCP e chama as ferramentas contra o banco real.
_TEM_BANCO = os.path.exists(".env") or bool(os.getenv("PG_HOST"))
pytestmark = pytest.mark.skipif(not _TEM_BANCO, reason="sem banco configurado")


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _payload(res):
    """Extrai o dict/lista retornado pela ferramenta (tolerante a versões do fastmcp)."""
    data = getattr(res, "data", None)
    if data is not None:
        return data
    sc = getattr(res, "structured_content", None)
    if sc is not None:
        return sc
    return json.loads(res.content[0].text)


@pytest.mark.anyio
async def test_ferramentas_ponta_a_ponta():
    mcp = montar()  # conecta no banco configurado via .env
    async with Client(mcp) as client:
        nomes = {t.name for t in await client.list_tools()}
        assert {"listar_tabelas", "descrever_tabela", "consultar"} <= nomes

        # consulta legítima de leitura (schema-agnóstica: roda em qualquer Postgres)
        r = await client.call_tool("consultar", {"sql": "SELECT 1 AS n"})
        p = _payload(r)
        assert p["linhas"][0]["n"] >= 0

        # tentativa de escrita: retorna erro tratado (não explode)
        w = await client.call_tool("consultar", {"sql": "DELETE FROM clientes"})
        assert _payload(w)["erro"] == "somente_leitura"

        # introspecção ponta a ponta (agnóstica ao schema do banco configurado)
        assert isinstance(_payload(await client.call_tool("listar_schemas", {})), list)
        tabelas = _payload(await client.call_tool("listar_tabelas", {"schema": "public"}))
        assert isinstance(tabelas, list)
        if tabelas:  # se houver alguma tabela em public, exercita descrever_tabela + amostra
            nome = tabelas[0]["table_name"]
            cols = _payload(await client.call_tool("descrever_tabela", {"tabela": nome}))
            assert isinstance(cols, list) and cols
            am = _payload(await client.call_tool("amostra", {"tabela": nome, "n": 1}))
            assert "linhas" in am or "erro" in am  # a allowlist pode barrar; ambos são válidos
