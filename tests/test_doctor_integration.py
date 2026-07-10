import os

import pytest

from pg_readonly_mcp.doctor import executar_doctor

# Roda só quando há banco configurado: um .env na raiz OU PG_HOST no ambiente.
_TEM_BANCO = os.path.exists(".env") or bool(os.getenv("PG_HOST"))
pytestmark = pytest.mark.skipif(
    not _TEM_BANCO, reason="sem banco configurado (crie .env ou defina PG_HOST)"
)


def test_doctor_passa_contra_o_banco_real(capsys):
    # roda as 6 checagens contra o banco do .env; exige VPN/rede ativa.
    codigo = executar_doctor(env_file=".env", yaml_file="config.yaml", modo_cor="never")
    saida = capsys.readouterr().out
    assert "== pg-readonly-mcp doctor ==" in saida
    assert codigo == 0, f"doctor falhou:\n{saida}"
