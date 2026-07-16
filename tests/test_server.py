import json

import pytest

from db_mcp.config import Settings
from db_mcp.errors import SomenteLeitura, SqlInvalido
from db_mcp.server import (
    Nucleo,
    _identificar_cliente,
    _validar_ident,
    _validar_qualificado,
    construir_servidor,
)


class FakeDB:
    def __init__(self):
        self.ultimo_sql = None

    def executar(self, sql, max_rows):
        self.ultimo_sql = sql
        return [{"ok": 1}], False


def _settings(monkeypatch, **over):
    base = {"pg_host": "h", "pg_dbname": "d", "pg_password": "p"}
    base.update(over)
    for k, v in base.items():
        monkeypatch.setenv(k.upper(), str(v))
    return Settings.load(env_file=None, yaml_file="/nao/existe.yaml")


def test_consultar_valida_e_injeta_limit(monkeypatch, tmp_path):
    s = _settings(monkeypatch, audit_log_path=str(tmp_path / "a.log"))
    nucleo = Nucleo(s, db=FakeDB())
    resp = nucleo.consultar("SELECT 1", cliente="t")
    assert resp["linhas"] == [{"ok": 1}]
    assert "LIMIT" in nucleo.db.ultimo_sql


def test_consultar_bloqueia_escrita(monkeypatch, tmp_path):
    s = _settings(monkeypatch, audit_log_path=str(tmp_path / "a.log"))
    nucleo = Nucleo(s, db=FakeDB())
    with pytest.raises(SomenteLeitura):
        nucleo.consultar("DELETE FROM t", cliente="t")


def test_consulta_rejeitada_entra_na_auditoria(monkeypatch, tmp_path):
    # A trilha de auditoria tem que registrar o que foi RECUSADO, não só o que passou —
    # é o evento de segurança que mais importa.
    log = tmp_path / "a.log"
    s = _settings(monkeypatch, audit_log_path=str(log))
    nucleo = Nucleo(s, db=FakeDB())

    with pytest.raises(SomenteLeitura):
        nucleo.consultar("DELETE FROM t", cliente="atacante")

    registro = json.loads(log.read_text(encoding="utf-8").strip())
    assert registro["veredito"] == "somente_leitura"
    assert registro["cliente"] == "atacante"


def test_erro_do_banco_e_auditado(monkeypatch, tmp_path):
    # Um erro vindo do banco (já embrulhado em ErroBanco pelo db.py) tem que virar
    # linha de auditoria, não escapar silencioso.
    from db_mcp.errors import ErroBanco

    class DBQuebrado:
        def executar(self, sql, max_rows):
            raise ErroBanco("erro do banco: relation inexistente")

    log = tmp_path / "a.log"
    s = _settings(monkeypatch, audit_log_path=str(log))
    nucleo = Nucleo(s, db=DBQuebrado())
    with pytest.raises(ErroBanco):
        nucleo.consultar("SELECT * FROM inexistente", cliente="t")
    assert json.loads(log.read_text(encoding="utf-8").strip())["veredito"] == "erro_banco"


def test_resultado_grande_demais_e_auditado(monkeypatch, tmp_path):
    from db_mcp.errors import ResultadoGrandeDemais

    class DBGrande:
        def executar(self, sql, max_rows):
            return [{"x": "A" * 1000}], False

    log = tmp_path / "a.log"
    s = _settings(monkeypatch, audit_log_path=str(log), max_result_bytes=10)
    nucleo = Nucleo(s, db=DBGrande())
    with pytest.raises(ResultadoGrandeDemais):
        nucleo.consultar("SELECT 1", cliente="t")
    assert (
        json.loads(log.read_text(encoding="utf-8").strip())["veredito"] == "resultado_grande_demais"
    )


def test_limite_de_taxa_via_nucleo_e_auditado(monkeypatch, tmp_path):
    from db_mcp.errors import LimiteDeTaxa

    log = tmp_path / "a.log"
    s = _settings(monkeypatch, audit_log_path=str(log), rate_limit_per_min=1)
    nucleo = Nucleo(s, db=FakeDB())
    nucleo.consultar("SELECT 1", cliente="t")  # gasta a única ficha
    with pytest.raises(LimiteDeTaxa):
        nucleo.consultar("SELECT 1", cliente="t")
    ultima = json.loads(log.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert ultima["veredito"] == "limite_de_taxa"


def test_truncado_pelo_caminho_completo(monkeypatch, tmp_path):
    # FakeDB devolve truncado=True; o Nucleo tem que propagar isso na resposta.
    class DBTruncado:
        def executar(self, sql, max_rows):
            return [{"n": 1}], True

    s = _settings(monkeypatch, audit_log_path=str(tmp_path / "a.log"))
    nucleo = Nucleo(s, db=DBTruncado())
    assert nucleo.consultar("SELECT 1", cliente="t")["truncado"] is True


def test_validar_ident_aceita_nomes_validos():
    assert _validar_ident("public") == "public"
    assert _validar_ident("minha_tabela") == "minha_tabela"


@pytest.mark.parametrize("mau", ["x' UNION SELECT 1", "a b", "a;b", "a'--", "", "1x"])
def test_validar_ident_bloqueia_injecao(mau):
    with pytest.raises(SqlInvalido):
        _validar_ident(mau)


def test_validar_qualificado_aceita_schema_tabela():
    assert _validar_qualificado("public.clientes") == "public.clientes"
    assert _validar_qualificado("clientes") == "clientes"


@pytest.mark.parametrize("mau", ["public.x' UNION SELECT 1", "a.b.c", "'; DROP", "public.a b"])
def test_validar_qualificado_bloqueia_injecao(mau):
    with pytest.raises(SqlInvalido):
        _validar_qualificado(mau)


def test_servidor_com_auth_token_configura_auth(monkeypatch):
    s = _settings(monkeypatch, auth_token="segredo")
    mcp = construir_servidor(s, conectar=False)
    assert mcp.auth is not None


def test_servidor_sem_auth_token_fica_sem_auth(monkeypatch):
    s = _settings(monkeypatch)
    mcp = construir_servidor(s, conectar=False)
    assert mcp.auth is None


def test_cli_recusa_http_sem_token(monkeypatch):
    # Fail-closed: em TRANSPORT=http sem AUTH_TOKEN o servidor não pode subir (senão o
    # endpoint HTTP ficaria aberto). A checagem acontece antes de tocar no banco.
    from db_mcp import cli

    for k, v in {"PG_HOST": "h", "PG_DBNAME": "d", "PG_PASSWORD": "p", "TRANSPORT": "http"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("AUTH_TOKEN", raising=False)
    monkeypatch.setattr("sys.argv", ["db-mcp", "--env", "/nao/existe", "run"])
    with pytest.raises(SystemExit):
        cli.main()


def test_identificar_cliente_sem_request_e_stdio():
    # Fora de uma request HTTP (stdio, testes) não há token: cai pra 'stdio'.
    assert _identificar_cliente() == "stdio"


def test_identificar_cliente_usa_client_id_do_token(monkeypatch):
    class _Token:
        client_id = "agente-x"

    monkeypatch.setattr("db_mcp.server.get_access_token", lambda: _Token())
    assert _identificar_cliente() == "agente-x"
