import pytest
import sqlglot

from db_mcp.config import Settings
from db_mcp.dialetos import DIALETOS_IMPLEMENTADOS, obter_dialeto
from db_mcp.dialetos.base import Perfil


def dialeto_ou_skip(nome: str):
    """Instancia o dialeto, ou pula se o driver dele não está instalado.

    Cada dialeto tem um extra OPCIONAL (`uv sync --extra mysql`) e o driver é
    importado no `__init__` — de propósito, pra `obter_dialeto` falhar cedo e o doctor
    dizer "instale o extra". Sem este guarda, registrar o mysql quebraria a suíte de
    quem clonou e rodou só `uv sync` (medido: ImportError, não skip).

    ⚠️ O CI DEVE instalar TODOS os extras — senão este skip silencia justamente o gate
    que existe pra pegar dialeto novo mal escrito.
    """
    try:
        return obter_dialeto(nome)
    except ImportError as e:
        pytest.skip(f"driver do dialeto {nome!r} não instalado ({e}); use --extra {nome}")


def test_obter_dialeto_postgres():
    d = obter_dialeto("postgres")
    assert d.nome == "postgres"
    assert d.sqlglot_dialeto == "postgres"
    assert d.schema_padrao == "public"


def test_dialeto_desconhecido_falha_com_erro_legivel():
    with pytest.raises(ValueError, match="dialeto desconhecido"):
        obter_dialeto("oracle")


def test_postgres_traz_as_funcoes_proibidas_do_banco():
    fp = obter_dialeto("postgres").funcs_proibidas
    assert "pg_read_file" in fp
    assert "query_to_xml" in fp
    assert "set_config" in fp
    # a lista é do dialeto, não global: função de OUTRO banco não entra aqui
    assert "load_file" not in fp  # MySQL
    assert "openquery" not in fp  # T-SQL


def test_sql_amostra_do_postgres_usa_limit_e_cita_o_nome():
    # identify=True cita o identificador ("clientes"): é o que faz o nome reservado
    # (Order -> [Order] no T-SQL) funcionar sem regex. No postgres sai com aspas duplas.
    sql = obter_dialeto("postgres").sql_amostra("clientes", 5)
    assert sql == 'SELECT * FROM "clientes" LIMIT 5'


def test_perfil_so_tem_somente_leitura_nesta_fase():
    # A escrita ganha spec próprio. O parâmetro existe pra costura ficar no lugar
    # certo, mas nesta fase só há um valor possível.
    assert [p.name for p in Perfil] == ["SOMENTE_LEITURA"]


@pytest.mark.parametrize("nome", DIALETOS_IMPLEMENTADOS)
def test_invariante_todo_dialeto(nome):
    # Gate pra TODO dialeto futuro (Fases 1 e 2), não só o postgres. Enumerado a partir
    # do _REGISTRO (fonte única): quem acrescentar um dialeto sem satisfazer isto quebra
    # o CI, não uma query em produção. Cobre os dois traps documentados no CLAUDE.md:
    d = dialeto_ou_skip(nome)
    # (a) sqlglot_dialeto tem que ser um nome que o sqlglot CONHECE — pega o clássico
    #     "sqlserver" (ValueError: Unknown dialect) escrito no lugar de "tsql".
    assert sqlglot.transpile("SELECT 1", read=d.sqlglot_dialeto, write=d.sqlglot_dialeto) == [
        "SELECT 1"
    ]
    # (b) funcs_proibidas NÃO pode ser vazia — é o único ponto da costura que falharia
    #     ABERTO: um stub com a lista por preencher liberaria load_file('/etc/passwd').
    assert d.funcs_proibidas, f"{nome}: funcs_proibidas vazia falharia ABERTA"


def test_sqlserver_nao_reusa_conexao():
    """O 'pool' do SQL Server abre conexão NOVA a cada checkout.

    O pymssql não tem pool (medido: nenhum símbolo 'pool' no módulo), e este dialeto é o
    único sem reset de sessão. Abrir nova por consulta é o que faz o gap desaparecer em
    vez de virar resíduo: sem reuso, não há estado a vazar. Este teste existe para
    impedir que alguém 'otimize' isso guardando a conexão.
    """
    # chamado só pelo efeito colateral: pula se o extra sqlserver não estiver instalado,
    # igual ao resto da suíte — _ConexaoPorConsulta em si não usa o pymssql.
    dialeto_ou_skip("sqlserver")
    abertas = []

    class _FakeConn:
        def __init__(self):
            abertas.append(self)
            self.fechada = False

        def close(self):
            self.fechada = True

    from db_mcp.dialetos.sqlserver import _ConexaoPorConsulta

    pool = _ConexaoPorConsulta(_FakeConn)
    with pool.connection() as c1:
        pass
    with pool.connection() as c2:
        pass

    assert len(abertas) == 2, "cada checkout tem que abrir uma conexão NOVA"
    assert c1 is not c2
    assert c1.fechada and c2.fechada, "a conexão tem que ser fechada ao sair do with"


def test_sqlserver_timeout_para_o_driver_nunca_e_zero(monkeypatch, tmp_path):
    """`statement_timeout_ms` abaixo de 1000 não pode virar `timeout=0` pro pymssql.

    Medido no docstring de `pymssql.connect`: "query timeout in seconds, default 0
    (no timeout)" — ali `0` não é "o mínimo possível", é "SEM timeout". A config
    (`Settings.statement_timeout_ms`) não tem `Field(ge=...)`: um operador pode
    legitimamente pedir 500ms, e `500 // 1000 == 0` desligaria o timeout em silêncio —
    o mesmo padrão de falha ABERTA que a Fase 1 mediu no MySQL (`pool_reset_session`
    zerando o `SET SESSION TRANSACTION READ ONLY` no checkout). O `max(1, ...)` em
    `_conectar` é a defesa; este teste existe para impedir que uma limpeza de código o
    troque de volta por divisão pura sem ninguém perceber.
    """
    d = dialeto_ou_skip("sqlserver")

    monkeypatch.setenv("DB_HOST", "h")
    monkeypatch.setenv("DB_DBNAME", "d")
    monkeypatch.setenv("DB_PASSWORD", "p")
    monkeypatch.setenv("STATEMENT_TIMEOUT_MS", "500")
    s = Settings.load(env_file=None, yaml_file=str(tmp_path / "inexistente.yaml"))
    assert s.statement_timeout_ms == 500  # a premissa do teste: abaixo de 1000

    capturado: dict = {}

    def _fake_connect(**kwargs):
        capturado.update(kwargs)

        class _FakeConn:
            def close(self) -> None:
                pass

        return _FakeConn()

    monkeypatch.setattr(d._pymssql, "connect", _fake_connect)

    d.conectar_doctor(s)

    assert capturado["timeout"] >= 1, "timeout=0 no pymssql significa SEM timeout"


def test_sqlserver_erro_readonly_nao_casa_229():
    """229 é 'permission denied on the object' — GENÉRICO.

    MEDIDO no SQL Server 2022: INSERT sem permissão dá 229, CREATE TABLE dá 262. Mas o
    229 também sobe quando falta SELECT. Se erro_readonly casasse 229, uma conexão que
    falhou por motivo NÃO relacionado seria classificada como 'somente-leitura
    confirmado' — o falso positivo perigoso, no cadeado que no SQL Server é o ÚNICO
    (não há read-only de sessão: SET TRANSACTION READ ONLY dá erro 156). Por isso o probe
    é CREATE TABLE e a lista é {262, 3906}.
    """
    d = dialeto_ou_skip("sqlserver")
    import pymssql

    def erro(numero):
        return pymssql.OperationalError(numero, b"mensagem qualquer")

    assert d.erro_readonly(erro(262)) is True  # CREATE TABLE permission denied
    assert d.erro_readonly(erro(3906)) is True  # database is read-only
    assert d.erro_readonly(erro(229)) is False  # GENÉRICO — não pode contar
    assert d.erro_readonly(ValueError("nada a ver")) is False


def test_sqlserver_timeout_exige_a_marca_20003():
    """🪤 O número do timeout não chega em args[0].

    MEDIDO (pymssql 2.3.13 / SQL Server 2022, com timeout=2 e WAITFOR DELAY '00:00:10'):
    levanta OperationalError(20047, b'...20003...Adaptive Server connection timed
    out...DBPROCESS is dead...'). O 20047 é genérico (qualquer conexão morta) e o 20003 —
    que identifica o timeout — só aparece no TEXTO. Casar 20003 em args[0] daria um
    predicado que NUNCA casa; casar 20047 puro classificaria queda de rede como timeout.
    """
    d = dialeto_ou_skip("sqlserver")
    import pymssql

    timeout = pymssql.OperationalError(
        20047, b"DB-Lib error message 20003, severity 6:\nAdaptive Server connection timed out\n"
    )
    rede = pymssql.OperationalError(20047, b"DB-Lib error message 20047:\nDBPROCESS is dead\n")

    assert d.erro_de_timeout(timeout) is True
    assert d.erro_de_timeout(rede) is False, "conexão morta sem timeout não é timeout"
    assert d.erro_de_timeout(ValueError("nada a ver")) is False


def test_sqlserver_erro_do_banco_so_pega_erro_do_driver():
    d = dialeto_ou_skip("sqlserver")
    import pymssql

    assert d.erro_do_banco(pymssql.OperationalError(208, b"Invalid object name")) is True
    assert d.erro_do_banco(ValueError("erro nosso, não do banco")) is False


def test_sqlserver_probe_de_escrita_e_create_table():
    # CREATE TABLE, não INSERT: o CREATE dá 262 (inequívoco) e o INSERT dá 229 (genérico).
    sql = dialeto_ou_skip("sqlserver").sql_probe_escrita()
    assert "CREATE TABLE" in sql.upper()
    assert "INSERT" not in sql.upper()


def test_sqlserver_sql_amostra_usa_top_e_colchetes():
    # T-SQL não tem LIMIT — o sqlglot emite TOP. identify=True cita com COLCHETES,
    # que é o que faz nome reservado (Order -> [Order]) funcionar sem regex.
    sql = dialeto_ou_skip("sqlserver").sql_amostra("clientes", 5)
    assert sql == "SELECT TOP 5 * FROM [clientes]"


def test_sqlserver_sql_amostra_recusa_nome_invalido():
    # SqlglotError, não ParseError: o tokenizer levanta TokenError, que é IRMÃ e não
    # filha — deixar vazar seria recusa sem auditoria.
    from db_mcp.errors import SqlInvalido

    with pytest.raises(SqlInvalido):
        dialeto_ou_skip("sqlserver").sql_amostra("nome 'nao fechado", 5)


def test_sqlserver_sql_identidade_nomeia_usuario_e_banco():
    # MEDIDO contra SQL Server 2022: devolve ('sa', 'master'). Os apelidos são o
    # contrato que mantém a chave do dict igual entre dialetos.
    sql = dialeto_ou_skip("sqlserver").sql_identidade()
    assert "AS usuario" in sql and "AS banco" in sql


def test_sqlserver_introspecao_passa_identificador_por_parametro():
    d = dialeto_ou_skip("sqlserver")
    sql, params = d.sql_introspecao("colunas", schema="dbo", tabela="clientes")
    assert "%s" in sql
    assert params == ("dbo", "clientes")
    assert "clientes" not in sql  # nunca concatenado


def test_sqlserver_introspecao_tipo_invalido_recusa():
    from db_mcp.errors import SqlInvalido

    with pytest.raises(SqlInvalido):
        dialeto_ou_skip("sqlserver").sql_introspecao("inexistente")
