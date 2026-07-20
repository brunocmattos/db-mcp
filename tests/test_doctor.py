import socket

import pytest

from db_mcp.doctor import (
    Contexto,
    PularChecagem,
    Resultado,
    checar_config,
    checar_tcp,
    rodar,
)


def _ok(ctx):
    "checagem que sempre passa"
    return Resultado(True, "sempre ok", "detalhe")


def _falha(ctx):
    "checagem que sempre falha"
    return Resultado(False, "sempre falha", "detalhe", "conserte assim")


def _pula(ctx):
    "checagem pulada"
    raise PularChecagem("pre-requisito faltando")


def _explode(ctx):
    "checagem que estoura"
    raise RuntimeError("boom")


def test_rodar_tudo_ok_retorna_0(capsys):
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    assert rodar([_ok, _ok], ctx, cor=False, emoji=False) == 0


def test_rodar_com_falha_retorna_1(capsys):
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    assert rodar([_ok, _falha], ctx, cor=False, emoji=False) == 1


def test_rodar_pulada_nao_conta_como_falha(capsys):
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    assert rodar([_ok, _pula], ctx, cor=False, emoji=False) == 0


def test_rodar_excecao_vira_falha_sem_derrubar(capsys):
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    assert rodar([_explode], ctx, cor=False, emoji=False) == 1
    assert "boom" in capsys.readouterr().out


def _limpar_pg(monkeypatch):
    for k in ("DB_HOST", "DB_PORT", "DB_DBNAME", "DB_PASSWORD"):
        monkeypatch.delenv(k, raising=False)


def test_checar_config_ok(monkeypatch):
    _limpar_pg(monkeypatch)
    for k, v in {"DB_HOST": "h", "DB_DBNAME": "d", "DB_PASSWORD": "p"}.items():
        monkeypatch.setenv(k, v)
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    r = checar_config(ctx)
    assert r.ok
    assert ctx.settings is not None
    assert ctx.settings.db_host == "h"


def test_checar_config_falta_campo_obrigatorio(monkeypatch):
    _limpar_pg(monkeypatch)  # sem DB_HOST/DB_DBNAME/DB_PASSWORD -> ValidationError
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    r = checar_config(ctx)
    assert not r.ok
    assert ctx.settings is None


def test_checar_tcp_ok(monkeypatch):
    _limpar_pg(monkeypatch)
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    porta = srv.getsockname()[1]
    for k, v in {
        "DB_HOST": "127.0.0.1",
        "DB_PORT": str(porta),
        "DB_DBNAME": "d",
        "DB_PASSWORD": "p",
    }.items():
        monkeypatch.setenv(k, v)
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    checar_config(ctx)
    try:
        r = checar_tcp(ctx)
    finally:
        srv.close()
    assert r.ok


def test_checar_tcp_recusado(monkeypatch):
    _limpar_pg(monkeypatch)
    for k, v in {
        "DB_HOST": "127.0.0.1",
        "DB_PORT": "1",
        "DB_DBNAME": "d",
        "DB_PASSWORD": "p",
    }.items():
        monkeypatch.setenv(k, v)
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    checar_config(ctx)
    r = checar_tcp(ctx)
    assert not r.ok


def test_checar_tcp_pula_sem_config():
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")  # settings=None
    with pytest.raises(PularChecagem):
        checar_tcp(ctx)


def test_saida_decorada_degrada_para_ascii(capsys):
    # Regressão: com encoding limitado (emoji=False), as decorações ↳ / — / · eram
    # impressas cruas e quebravam com UnicodeEncodeError (console cp1252 / pipe ascii).
    # Toda a saída decorativa deve ser ASCII quando emoji=False.
    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    rodar([_ok, _falha, _pula], ctx, cor=False, emoji=False)
    out = capsys.readouterr().out
    out.encode("ascii")  # não pode levantar UnicodeEncodeError
    assert "->" in out  # a seta ↳ virou ASCII na linha de remediação
