import pytest
from pydantic import ValidationError

from db_mcp.config import Settings


def test_env_tem_prioridade_sobre_yaml(tmp_path, monkeypatch):
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("max_rows: 50\ntransport: stdio\n", encoding="utf-8")
    monkeypatch.setenv("PG_HOST", "db.exemplo")
    monkeypatch.setenv("PG_DBNAME", "banco")
    monkeypatch.setenv("PG_PASSWORD", "segredo")
    monkeypatch.setenv("MAX_ROWS", "7")  # env deve vencer o yaml

    s = Settings.load(env_file=None, yaml_file=str(yaml_file))

    assert s.pg_host == "db.exemplo"
    assert s.pg_user == "mcp_ro"  # default
    assert s.max_rows == 7  # env venceu (yaml era 50)
    assert s.transport == "stdio"  # veio do yaml


def test_falta_de_segredo_obrigatorio_falha(monkeypatch, tmp_path):
    monkeypatch.delenv("PG_HOST", raising=False)
    monkeypatch.delenv("PG_DBNAME", raising=False)
    monkeypatch.delenv("PG_PASSWORD", raising=False)
    with pytest.raises(ValidationError):
        Settings.load(env_file=None, yaml_file=str(tmp_path / "inexistente.yaml"))


def test_load_nao_polui_estado_de_classe(tmp_path, monkeypatch):
    # load() não pode gravar env_file/yaml_file no model_config da classe (estado
    # global compartilhado) — senão um load contamina os seguintes e outras threads.
    monkeypatch.setenv("PG_HOST", "h")
    monkeypatch.setenv("PG_DBNAME", "d")
    monkeypatch.setenv("PG_PASSWORD", "p")
    yaml_file = tmp_path / "c.yaml"
    yaml_file.write_text("max_rows: 33\n", encoding="utf-8")

    s = Settings.load(env_file=None, yaml_file=str(yaml_file))

    assert s.max_rows == 33  # leu o yaml passado
    assert Settings.model_config.get("env_file") is None
    assert Settings.model_config.get("yaml_file") is None


def test_dialeto_default_e_postgres(tmp_path, monkeypatch):
    for k, v in {"PG_HOST": "h", "PG_DBNAME": "d", "PG_PASSWORD": "p"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("DIALETO", raising=False)

    s = Settings.load(env_file=None, yaml_file=str(tmp_path / "inexistente.yaml"))

    assert s.dialeto == "postgres"


def test_dialeto_invalido_e_recusado_na_subida(tmp_path, monkeypatch):
    # Fail-fast: um dialeto que não existe não pode passar da validação e só explodir
    # lá na frente, na hora de conectar.
    for k, v in {"PG_HOST": "h", "PG_DBNAME": "d", "PG_PASSWORD": "p"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("DIALETO", "oracle")

    with pytest.raises(ValidationError):
        Settings.load(env_file=None, yaml_file=str(tmp_path / "inexistente.yaml"))


def test_loads_seguidos_nao_vazam_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("PG_HOST", "h")
    monkeypatch.setenv("PG_DBNAME", "d")
    monkeypatch.setenv("PG_PASSWORD", "p")
    y1 = tmp_path / "a.yaml"
    y1.write_text("max_rows: 11\n", encoding="utf-8")
    y2 = tmp_path / "b.yaml"
    y2.write_text("max_rows: 22\n", encoding="utf-8")

    s1 = Settings.load(env_file=None, yaml_file=str(y1))
    s2 = Settings.load(env_file=None, yaml_file=str(y2))

    assert (s1.max_rows, s2.max_rows) == (11, 22)
