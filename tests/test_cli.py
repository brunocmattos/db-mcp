import sys

import pytest

import db_mcp.cli as cli
from db_mcp.cli import montar


def test_montar_retorna_servidor(monkeypatch):
    for k, v in {"PG_HOST": "h", "PG_DBNAME": "d", "PG_PASSWORD": "p"}.items():
        monkeypatch.setenv(k, v)
    # conectar=False não abre conexão com o banco
    mcp = montar(env_file=None, yaml_file="/nao/existe.yaml", conectar=False)
    assert mcp.name == "db-mcp"


def test_doctor_subcomando_propaga_exit_code(monkeypatch):
    chamado = {}

    def fake_doctor(env_file, yaml_file, modo_cor):
        chamado["args"] = (env_file, yaml_file, modo_cor)
        return 3

    monkeypatch.setattr("db_mcp.doctor.executar_doctor", fake_doctor)
    monkeypatch.setattr(sys, "argv", ["db-mcp", "doctor"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 3
    assert chamado["args"] == (".env", "config.yaml", "auto")


def test_flag_dialect_sobrescreve_a_config(monkeypatch):
    for k in ("PG_HOST", "PG_DBNAME", "PG_PASSWORD"):
        monkeypatch.setenv(k, "x")
    monkeypatch.delenv("DIALETO", raising=False)
    visto = {}

    def _captura(s, conectar=True):
        visto["dialeto"] = s.dialeto
        raise SystemExit(0)  # não sobe servidor de verdade no teste

    monkeypatch.setattr(cli, "construir_servidor", _captura)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "db-mcp",
            "--env",
            "naoexiste.env",
            "--config",
            "naoexiste.yaml",
            "--dialect",
            "mysql",
            "run",
        ],
    )
    with pytest.raises(SystemExit):
        cli.main()
    assert visto["dialeto"] == "mysql"


def test_http_sem_auth_token_recusa_subir(monkeypatch):
    # fail-closed: TRANSPORT=http sem AUTH_TOKEN nao pode subir (ficaria sem auth).
    for k in ("PG_HOST", "PG_DBNAME", "PG_PASSWORD"):
        monkeypatch.setenv(k, "x")
    monkeypatch.setenv("TRANSPORT", "http")
    monkeypatch.delenv("AUTH_TOKEN", raising=False)

    def _nao_constroi(*a, **k):
        raise AssertionError("fail-closed regrediu: nao deveria construir/subir o servidor")

    monkeypatch.setattr(cli, "construir_servidor", _nao_constroi)
    monkeypatch.setattr(
        sys,
        "argv",
        ["db-mcp", "--env", "naoexiste.env", "--config", "naoexiste.yaml", "run"],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert "AUTH_TOKEN" in str(exc.value)
