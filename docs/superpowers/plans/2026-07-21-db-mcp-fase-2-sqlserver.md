# Fase 2 — dialeto SQL Server: plano de implementação

> **Para executores agênticos:** SUB-SKILL OBRIGATÓRIA — use `superpowers:subagent-driven-development`
> (recomendado) ou `superpowers:executing-plans` para implementar task a task. Os passos usam
> checkbox (`- [ ]`) para acompanhamento.

**Goal:** o db-mcp falar com um terceiro banco — `db-mcp --dialect sqlserver doctor` fechando
6/6 contra um SQL Server real, com a suíte verde nos três bancos.

**Architecture:** um módulo novo (`dialetos/sqlserver.py`) implementando o Protocol `Dialeto`,
mais uma linha no `_REGISTRO`. **Nenhum arquivo do núcleo muda.** A conexão é **sem pool** (o
pymssql não tem um) — cada `.connection()` abre uma conexão nova, o que elimina por construção
a classe de bug do reset de sessão.

**Tech Stack:** Python 3.11+, uv, pymssql 2.3+, sqlglot (dialeto `tsql`), pytest, Docker.

**Spec:** [2026-07-21-db-mcp-fase-2-sqlserver-design.md](../specs/2026-07-21-db-mcp-fase-2-sqlserver-design.md) —
tudo marcado 📏 lá foi medido. Este plano não repete as justificativas; consulte o spec.

**Este plano é deliberadamente enxuto.** A Fase 1 gastou 1.591 linhas de plano para produzir um
arquivo de 190 — o corte certo é na meta-documentação, não nas tasks.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `src/db_mcp/dialetos/sqlserver.py` | **novo** — tudo que é específico do SQL Server |
| `src/db_mcp/dialetos/__init__.py` | +1 fábrica, +1 linha no `_REGISTRO` |
| `pyproject.toml` | extra opcional `sqlserver` |
| `tests/test_sql_sqlserver.py` | **novo** — corpus de ataque do T-SQL |
| `demo/init-sqlserver/{01,02,03}.sql` | **novos** — schema, seed, usuário read-only + DENY |
| `docker-compose.yml` | profile `sqlserver` |
| `.github/workflows/ci.yml` | job `integration-sqlserver` |
| `docs/`, `CHANGELOG.md`, `CLAUDE.md` | tabela dos cadeados + receita de DENY |

**Pré-requisito para as tasks 3-9:** um SQL Server de pé. Suba com
`docker compose --profile sqlserver up -d` depois da Task 6; antes dela, use um descartável:

```bash
docker run -d --name mssql-dev -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD=Sonda_MCP_2026!" \
  -e "MSSQL_PID=Developer" -p 1434:1433 mcr.microsoft.com/mssql/server:2022-latest
```

⚠️ **Derrube o que você subir** (`docker rm -f mssql-dev`) ao terminar de usar.

---

### Task 1: Registrar o dialeto e fazer o gate de invariante falhar

**Files:**
- Modify: `pyproject.toml` (seção `[project.optional-dependencies]`)
- Create: `src/db_mcp/dialetos/sqlserver.py`
- Modify: `src/db_mcp/dialetos/__init__.py`

- [ ] **Step 1: Adicionar o extra opcional**

Em `pyproject.toml`, logo abaixo da linha do `mysql = [...]`:

```toml
# Driver do SQL Server — pymssql NÃO tem pool nem reset de sessão (medido: nenhum
# símbolo "pool" no módulo). Por isso o dialeto abre conexão por consulta; ver §3 do
# spec da Fase 2. pyodbc daria pooling via gerenciador ODBC, mas exige msodbcsql18 no SO.
sqlserver = ["pymssql>=2.3"]
```

- [ ] **Step 2: Instalar e verificar**

Run: `uv sync --all-extras`
Expected: instala `pymssql`, sem erro.

- [ ] **Step 3: Escrever o esqueleto do dialeto**

Crie `src/db_mcp/dialetos/sqlserver.py`.

⚠️ **`Dialeto` é um Protocol ESTRUTURAL: o mypy exige TODOS os membros, não só os que esta
task usa.** Um esqueleto com apenas `schema_padrao`/`criar_pool`/`conectar_doctor` faz
`_sqlserver() -> Dialeto` falhar com
`Incompatible return value type (got "DialetoSqlServer", expected "Dialeto")`. Por isso os
demais membros entram já aqui como `raise NotImplementedError`, cada um marcado com a task
que o preenche.

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

    from ..config import Settings
    from .base import PoolLike

# Placeholder proposital: a Task 2 preenche. Vazia aqui para o gate de invariante
# FALHAR primeiro (é o teste que prova que o gate funciona).
FUNCS_PROIBIDAS_SQLSERVER: frozenset[str] = frozenset()


class DialetoSqlServer:
    # 🪤 nome != sqlglot_dialeto. No sqlglot o SQL Server é "tsql"; "sqlserver" levanta
    # ValueError em TODA query — e uma recusa que não é McpDbError escapa da auditoria.
    nome = "sqlserver"
    sqlglot_dialeto = "tsql"
    funcs_proibidas = FUNCS_PROIBIDAS_SQLSERVER
    porta_padrao = 1433

    def __init__(self) -> None:
        import pymssql  # lazy: o extra `sqlserver` só é exigido de quem usa SQL Server

        self._pymssql = pymssql

    @property
    def schema_padrao(self) -> str:
        return "dbo"

    def criar_pool(self, s: Settings) -> PoolLike:
        raise NotImplementedError  # Task 3

    def conectar_doctor(self, s: Settings) -> Any:
        raise NotImplementedError  # Task 3

    # --- Placeholders restantes do Protocol Dialeto -----------------------------
    #
    # Sem eles o mypy strict recusa `_sqlserver() -> Dialeto` (Protocol estrutural
    # exige TODOS os membros, não só os que o T1 usa). Cada um preenche na task
    # marcada no comentário.

    def probar_escrita(self, conn: Any) -> None:
        raise NotImplementedError  # Task 4

    def erro_readonly(self, e: Exception) -> bool:
        raise NotImplementedError  # Task 4

    def erro_de_timeout(self, e: Exception) -> bool:
        raise NotImplementedError  # Task 4

    def erro_do_banco(self, e: Exception) -> bool:
        raise NotImplementedError  # Task 4

    def linhas_como_dict(self, conn: Any) -> AbstractContextManager[Any]:
        raise NotImplementedError  # Task 5

    def sql_amostra(self, tabela: str, n: int) -> str:
        raise NotImplementedError  # Task 5

    def sql_probe_escrita(self) -> str:
        raise NotImplementedError  # Task 4

    def sql_identidade(self) -> str:
        raise NotImplementedError  # Task 5

    def sql_introspecao(
        self, tipo: str, schema: str | None = None, tabela: str | None = None
    ) -> tuple[str, tuple[Any, ...]]:
        raise NotImplementedError  # Task 5
```

- [ ] **Step 4: Registrar no `_REGISTRO`**

Em `src/db_mcp/dialetos/__init__.py`, adicione a fábrica depois de `_mysql`:

```python
def _sqlserver() -> Dialeto:
    from .sqlserver import DialetoSqlServer

    return DialetoSqlServer()
```

e a linha no dict:

```python
_REGISTRO: dict[str, Callable[[], Dialeto]] = {
    "postgres": _postgres,
    "mysql": _mysql,
    "sqlserver": _sqlserver,
}
```

- [ ] **Step 5: Rodar o gate e ver a falha ESPERADA**

Run: `uv run pytest tests/test_dialetos.py -q -k sqlserver`
Expected: **FAIL** em `test_invariante_todo_dialeto[sqlserver]` com
`AssertionError: sqlserver: funcs_proibidas vazia falharia ABERTA`.

> Esta falha é o objetivo da task: prova que o gate pega dialeto novo mal preenchido.
> A parte (a) do invariante (`sqlglot.transpile` com `tsql`) já deve passar — se falhar com
> `Unknown dialect`, você escreveu `"sqlserver"` no `sqlglot_dialeto`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/db_mcp/dialetos/sqlserver.py src/db_mcp/dialetos/__init__.py
git commit -m "feat(dialeto): esqueleto do sqlserver + extra opcional (T1)"
```

---

### Task 1b: destravar o teste de "dialeto indisponível"

> **Por que esta task existe:** registrar `"sqlserver"` no `_REGISTRO` (Task 1, Step 4) **quebra**
> `tests/test_doctor.py::test_checar_config_dialeto_sem_implementacao`. Aquele teste tomava
> emprestado, como cenário, o acidente de existir um valor do `Literal` do config sem fábrica no
> `_REGISTRO`. Já quebrou por isso na Fase 1 T5 (o alvo era `"mysql"` e migrou para `"sqlserver"`),
> e agora **não sobra alvo** — os três dialetos existem. Não é regressão da Task 1: é consequência
> estrutural de completá-la.

**Files:**
- Modify: `tests/test_doctor.py:127-145`

- [ ] **Step 1: Reescrever o teste construindo o cenário**

O sujeito real do teste não é "existe um dialeto por implementar" — é **"quando `obter_dialeto`
falha, `checar_config` recusa com mensagem legível e as checagens seguintes se PULAM em vez de
estourar"**. Isso se testa direto, e aí o teste vale para sempre.

`src/db_mcp/doctor.py:15` faz `from .dialetos import Dialeto, obter_dialeto` — o nome está ligado
no módulo do doctor, então o alvo estável é **`db_mcp.doctor.obter_dialeto`**. A linha 191 é
`except Exception`, então qualquer exceção serve.

Cubra **os dois motivos** que a remediação (linhas 196-197) promete — "sem implementação **ou**
driver não instalado" — porque hoje só um é exercitado:

```python
@pytest.mark.parametrize(
    "exc",
    [
        ValueError("dialeto desconhecido: 'oracle'"),  # sem implementação
        ImportError("No module named 'pymssql'"),  # extra do driver faltando
    ],
    ids=["sem-implementacao", "driver-faltando"],
)
def test_checar_config_dialeto_indisponivel(monkeypatch, exc):
    # O cenário é CONSTRUÍDO, não tomado emprestado. A versão anterior deste teste
    # dependia de existir um valor do Literal do config SEM fábrica no _REGISTRO — e por
    # isso quebrou DUAS vezes: na Fase 1 T5 (o alvo era "mysql", que passou a existir) e na
    # Fase 2 T1 (o alvo virou "sqlserver", que também passou a existir). Com os três
    # dialetos implementados não sobra alvo emprestável. Fazendo o `obter_dialeto` falhar
    # direto, o teste passa a exercitar o que realmente importa — a remediação do doctor —
    # e não depende de qual dialeto por acaso ainda não existe.
    _limpar_pg(monkeypatch)
    for k, v in {"DB_HOST": "h", "DB_DBNAME": "d", "DB_PASSWORD": "p"}.items():
        monkeypatch.setenv(k, v)

    def _falha(_nome):
        raise exc

    monkeypatch.setattr("db_mcp.doctor.obter_dialeto", _falha)

    ctx = Contexto(env_file=None, yaml_file="/nao/existe.yaml")
    r = checar_config(ctx)
    assert not r.ok
    assert r.titulo == "Dialeto indisponível"
    assert ctx.dialeto is None  # as checagens seguintes se PULAM, não estouram
    with pytest.raises(PularChecagem):
        checar_tcp(ctx)
```

- [ ] **Step 2: Rodar**

Run: `uv run pytest tests/test_doctor.py -q`
Expected: PASS, com os dois casos parametrizados.

Run: `uv run pytest -q`
Expected: o **único** vermelho é `test_invariante_todo_dialeto[sqlserver]` — o objetivo da Task 1.

- [ ] **Step 3: Commit**

```bash
git add tests/test_doctor.py
git commit -m "test(doctor): cenario de dialeto indisponivel deixa de depender de dialeto por implementar (T1b)"
```

---

### Task 2: `funcs_proibidas` e o corpus de ataque do T-SQL

**Files:**
- Modify: `src/db_mcp/dialetos/sqlserver.py`
- Create: `tests/test_sql_sqlserver.py`

- [ ] **Step 1: Escrever os testes que falham**

Crie `tests/test_sql_sqlserver.py`:

```python
"""Corpus de ataque do dialeto SQL Server (Fase 2 T2).

Arquivo separado de propósito, igual ao `test_sql_mysql.py`: o driver é um extra
OPCIONAL, e o `importorskip` abaixo faz o módulo inteiro se pular sem derrubar a
suíte de quem não instalou o extra.

Mesmo mecanismo (`validar`), lista diferente — a tese do projeto em forma de teste.
"""

import pytest

pytest.importorskip("pymssql", reason="extra `sqlserver` não instalado")

from db_mcp.dialetos import obter_dialeto
from db_mcp.dialetos.base import Perfil
from db_mcp.errors import McpDbError, SomenteLeitura
from db_mcp.guardrails.sql import validar

SS = obter_dialeto("sqlserver")


def _recusa(sql: str) -> None:
    with pytest.raises(McpDbError):
        validar(sql, SS, Perfil.SOMENTE_LEITURA)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM OPENQUERY(srv, 'SELECT 1')",
        "SELECT * FROM OPENDATASOURCE('SQLNCLI','x').db.dbo.t",
        "SELECT * FROM xp_cmdshell('dir')",
        "SELECT * FROM fn_get_audit_file('x', NULL, NULL)",
        "SELECT * FROM fn_trace_gettable('x', 1)",
    ],
)
def test_funcoes_perigosas_sao_recusadas_pela_blocklist(sql):
    # MEDIDO: estas chegam como exp.Anonymous e passam a checagem de raiz Select.
    # Quem barra é funcs_proibidas — o mecanismo já existe, a lista é do dialeto.
    with pytest.raises(SomenteLeitura, match="função não permitida"):
        validar(sql, SS, Perfil.SOMENTE_LEITURA)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT [xp_cmdshell]('dir')",
        'SELECT "xp_cmdshell"(\'dir\')',
    ],
)
def test_citacao_nao_escapa_da_blocklist(sql):
    # 🪤 No T-SQL aspas duplas são CITAÇÃO de identificador — o OPOSTO do MySQL, onde
    # são STRING. O caso do Postgres porta pra cá; o do MySQL NÃO. `.name` normaliza.
    with pytest.raises(SomenteLeitura, match="função não permitida"):
        validar(sql, SS, Perfil.SOMENTE_LEITURA)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM OPENROWSET('SQLNCLI', 'srv';'u';'p', 'SELECT 1')",
        "SELECT * FROM OPENROWSET(BULK 'C:\\x.txt', SINGLE_CLOB) AS a",
        "WAITFOR DELAY '00:00:10'",
        "EXECUTE AS LOGIN = 'sa'",
        "SELECT 1\nGO\nDROP TABLE t",
    ],
)
def test_recusados_hoje_apenas_por_parseerror(sql):
    # ⚠️ REGRESSÃO DELIBERADA. Estes falham FECHADO por ACIDENTE: o sqlglot não os
    # parseia, então morrem em SqlInvalido. Se uma versão nova passar a parseá-los, eles
    # viram Select com raiz válida e escapam. O teste exige RECUSA (McpDbError), NÃO o
    # mecanismo — assim ele AVISA em vez de o buraco abrir calado. Mesmo padrão do
    # INTO OUTFILE no MySQL (test_sql_mysql.py).
    _recusa(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO t VALUES (1)",
        "SELECT * INTO nova FROM t",
        "EXEC sp_who",
        "EXEC xp_cmdshell 'dir'",
        "EXEC sp_executesql N'SELECT 1'",
    ],
)
def test_escrita_e_execucao_sao_recusadas(sql):
    _recusa(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT TOP 10 * FROM t",
        "WITH c AS (SELECT 1 AS x) SELECT * FROM c",
        "SELECT 1 UNION SELECT 2",
        "SELECT * FROM t FOR XML AUTO",
    ],
)
def test_select_legitimo_passa(sql):
    validar(sql, SS, Perfil.SOMENTE_LEITURA)  # não levanta


def test_lista_e_do_dialeto_nao_global():
    fp = SS.funcs_proibidas
    assert "openquery" in fp
    assert "xp_cmdshell" in fp
    assert "load_file" not in fp  # MySQL
    assert "pg_read_file" not in fp  # Postgres
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_sql_sqlserver.py -q`
Expected: FAIL — os testes de blocklist falham porque `funcs_proibidas` está vazia.

- [ ] **Step 3: Preencher a lista**

Em `src/db_mcp/dialetos/sqlserver.py`, substitua o placeholder:

```python
# O mecanismo (exp.Anonymous + nome) fica no validador; só a lista é do dialeto.
# Defesa em profundidade: o limite real é o GRANT (medido: CREATE recusa com 262).
# Esta lista existe pro que o GRANT NÃO barra.
#
# Enumerada, NÃO um prefixo "xp_*": um prefixo daria falsa cobertura (as fn_* ficariam
# de fora) e barraria nome de usuário que por acaso comece com xp_.
FUNCS_PROIBIDAS_SQLSERVER = frozenset(
    {
        # saem do banco/instância — o vetor mais grave do SQL Server. MEDIDO: chegam
        # como exp.Anonymous e passam a checagem de raiz; só a blocklist os pega.
        "openquery",
        "opendatasource",
        "openrowset",
        # execução de comando no SO e leitura de disco/registro
        "xp_cmdshell",
        "xp_regread",
        "xp_regwrite",
        "xp_dirtree",
        "xp_fileexist",
        "xp_subdirs",
        "xp_msver",
        # leem trilha de auditoria e trace do servidor
        "fn_get_audit_file",
        "fn_trace_gettable",
        # enumera permissões — reconhecimento
        "fn_my_permissions",
    }
)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/test_sql_sqlserver.py tests/test_dialetos.py -q`
Expected: PASS em tudo, incluindo `test_invariante_todo_dialeto[sqlserver]`.

- [ ] **Step 5: Commit**

```bash
git add src/db_mcp/dialetos/sqlserver.py tests/test_sql_sqlserver.py
git commit -m "feat(sqlserver): funcs_proibidas + corpus de ataque do T-SQL (T2)"
```

---

### Task 2b: honestidade da blocklist (achados da revisão)

> **Feita em `8050883`.** A revisão independente da T2 mediu contra um SQL Server 2022 real e
> derrubou uma afirmação deste plano. Registrado aqui porque a lição vale para quem mantiver a
> lista — a versão final do comentário está em `src/db_mcp/dialetos/sqlserver.py`.

**A lista tem dois grupos com forças MUITO diferentes, e a primeira redação não distinguia:**

*Grupo A — a blocklist é mesmo quem barra.* `openquery`, `opendatasource`, `openrowset`,
`fn_get_audit_file`, `fn_trace_gettable`, `fn_my_permissions`, `fn_dblog`, `fn_dump_dblog`.
Executam como função/rowset dentro de um `SELECT`, chegam como `exp.Anonymous`, passam a
checagem de raiz. **Apagar uma entrada daqui abre um buraco real.**

*Grupo B — sobra-defesa deliberada.* `xp_cmdshell`, `xp_regread`, `xp_regwrite`, `xp_dirtree`,
`xp_fileexist`, `xp_subdirs`, `xp_msver`. São **stored procedures estendidas** — só invocáveis
por `EXEC`, nunca como função num `SELECT`. Medido **como `sa`**, para eliminar o GRANT como
variável:

```
SELECT * FROM xp_cmdshell('dir')  ->  Msg 208: Invalid object name 'xp_cmdshell'.
SELECT xp_cmdshell('dir')         ->  Msg 195: 'xp_cmdshell' is not a recognized built-in function name.
```

O motor recusa a sintaxe para **qualquer** usuário; a forma real (`EXEC xp_cmdshell ...`) morre
na checagem de raiz. **Apagar uma entrada daqui não muda nada.** Ficam na lista porque
sobra-defesa é barata — mas dizer que "só a blocklist as pega" era falso.

**Os três outros achados, todos corrigidos no mesmo commit:**

1. **`openrowset` estava na lista sem teste que provasse o caminho até ela.** As formas do
   corpus (credencial com `;`, e `BULK`) morrem no `ParseError`. A forma **padrão de 3
   argumentos** — a técnica clássica de escalonamento via loopback — parseia e chega na
   blocklist. Sem teste dela, apagar `"openrowset"` do frozenset deixava a suíte **inteira
   verde**. Provado por TDD: removendo a entrada, 3 casos falham com `DID NOT RAISE`.
2. **Faltavam `fn_dblog` e `fn_dump_dblog`** — leem o log de transação (expõem valores de linhas
   alteradas/apagadas), mesma categoria das já incluídas. Entraram com teste.
3. **Dois marcadores de task errados** no esqueleto: `probar_escrita` e `sql_probe_escrita`
   nascem juntos na **Task 4** (o primeiro chama o segundo).

⚠️ **Regra que fica para a Task 6 em diante:** ao acrescentar nome à blocklist, acrescente
também um caso ao corpus que prove o caminho **até ela**. Entrada sem teste é entrada que
alguém apaga sem a suíte notar.

---

### Task 3: Conexão sem pool

**Files:**
- Modify: `src/db_mcp/dialetos/sqlserver.py`
- Test: `tests/test_dialetos.py`

- [ ] **Step 1: Escrever o teste que falha**

Acrescente ao fim de `tests/test_dialetos.py`:

```python
def test_sqlserver_nao_reusa_conexao():
    """O 'pool' do SQL Server abre conexão NOVA a cada checkout.

    O pymssql não tem pool (medido: nenhum símbolo 'pool' no módulo), e este dialeto é o
    único sem reset de sessão. Abrir nova por consulta é o que faz o gap desaparecer em
    vez de virar resíduo: sem reuso, não há estado a vazar. Este teste existe para
    impedir que alguém 'otimize' isso guardando a conexão.
    """
    d = dialeto_ou_skip("sqlserver")
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_dialetos.py::test_sqlserver_nao_reusa_conexao -q`
Expected: FAIL com `ImportError: cannot import name '_ConexaoPorConsulta'`.

- [ ] **Step 3: Implementar**

Em `src/db_mcp/dialetos/sqlserver.py`, adicione os imports no topo:

```python
from collections.abc import Callable, Iterator
from contextlib import contextmanager
```

e a classe, antes de `DialetoSqlServer`:

```python
class _ConexaoPorConsulta:
    """`PoolLike` sem pool: cada `.connection()` abre uma conexão nova.

    O pymssql não tem pool (medido) e o SQL Server não tem reset de sessão — não existe
    `DISCARD ALL` nem `RESET CONNECTION`. Reusar conexão aqui exigiria reimplementar à mão
    justamente a peça que falhou ABERTA e em silêncio no MySQL (`pool_reset_session`
    zerando o read-only). Conexão nova É o reset.

    Custo medido: handshake ~14,3 ms (15,61 ms conexão nova vs 1,28 ms reusada), ~1% do
    round-trip percebido numa consulta via MCP. Ver §3 do spec.
    """

    def __init__(self, conectar: Callable[[], Any]) -> None:
        self._conectar = conectar

    @contextmanager
    def connection(self) -> Iterator[Any]:
        conn = self._conectar()
        try:
            yield conn
        finally:
            conn.close()  # sem pool: close() FECHA de verdade

    def close(self) -> None:
        """No-op: não há nada retido. Existe só para satisfazer `PoolLike`."""
```

e implemente os dois métodos que estavam `NotImplementedError`:

> 🪤 **Dois detalhes medidos na execução, que este snippet não previa:**
>
> **(a) O stub do pymssql tipa `port` como `str`, não `int`** — as 3 sobrecargas de `connect`
> em `_pymssql.pyi` declaram `port: str = ...`. Sem `str(...)`, o mypy recusa por nenhuma
> sobrecarga bater. Não é supressão: é o tipo que a lib espera.
>
> **(b) 🔴 `timeout=0` no pymssql significa SEM TIMEOUT**, não "timeout mínimo" (medido no
> docstring de `connect`). E `config.py:41` tem `statement_timeout_ms: int = 5000` **sem
> validação de mínimo**. Logo, `STATEMENT_TIMEOUT_MS=500` — meio segundo, pedido razoável —
> truncaria para `0` na divisão inteira e **desligaria o timeout em silêncio**: o mesmo padrão
> de falha ABERTA da Fase 1, só que por aritmética em vez de reset de sessão. O `max(1, ...)`
> não é arredondamento cosmético, é a proteção — e por isso ganhou regressão própria (Task 3b).

```python
    def _conectar(self, s: Settings) -> Any:
        return self._pymssql.connect(
            server=s.db_host,
            # o stub do pymssql tipa `port` como str (medido: as 3 sobrecargas de
            # `connect` em _pymssql.pyi declaram `port: str = ...`) — sem o str() o
            # mypy recusa por nenhuma sobrecarga bater com int.
            port=str(s.db_port or self.porta_padrao),
            database=s.db_dbname,
            user=s.db_user,
            password=s.db_password,
            autocommit=True,
            login_timeout=5,
            # timeout de query é client-side: não existe statement_timeout de servidor
            # como no Postgres nem max_execution_time como no MySQL. O max(1, ...) não é
            # só arredondamento: no pymssql `timeout=0` significa SEM timeout (medido no
            # docstring de `connect`), então statement_timeout_ms < 1000 truncado por
            # divisão inteira viraria 0 e desligaria o timeout em silêncio — o mesmo
            # padrão de falha ABERTA da Fase 1. Arredondar pra cima (timeout > pedido)
            # é o preço aceitável pra nunca cair nesse 0.
            timeout=max(1, s.statement_timeout_ms // 1000),
        )

    def criar_pool(self, s: Settings) -> PoolLike:
        return _ConexaoPorConsulta(lambda: self._conectar(s))

    def conectar_doctor(self, s: Settings) -> Any:
        # ⚠️ Mesma conexão de sempre, sem nenhum cadeado de aplicação — porque não existe
        # nenhum (medido: SET TRANSACTION READ ONLY dá erro 156). O doctor verifica o
        # cadeado nº 1 (o GRANT); se ele mesmo trancasse a sessão, o probe testaria o
        # próprio cadeado e um usuário gravável passaria como "somente-leitura".
        return self._conectar(s)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/test_dialetos.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/db_mcp/dialetos/sqlserver.py tests/test_dialetos.py
git commit -m "feat(sqlserver): conexao por consulta, sem pool (T3)"
```

---

### Task 4: `erro_readonly` — e o falso positivo do 229

**Files:**
- Modify: `src/db_mcp/dialetos/sqlserver.py`
- Test: `tests/test_dialetos.py`

- [ ] **Step 1: Escrever o teste que falha**

Acrescente a `tests/test_dialetos.py`:

```python
def test_sqlserver_erro_readonly_nao_casa_229():
    """229 é 'permission denied on the object' — GENÉRICO.

    MEDIDO no SQL Server 2022: INSERT sem permissão dá 229, CREATE TABLE dá 262. Mas o
    229 também sobe quando falta SELECT. Se erro_readonly casasse 229, uma conexão que
    falhou por motivo NÃO relacionado seria classificada como 'somente-leitura
    confirmado' — o falso positivo perigoso, no cadeado que no SQL Server é o ÚNICO
    (não há read-only de sessão). Por isso o probe é CREATE TABLE e a lista é {262, 3906}.
    """
    d = dialeto_ou_skip("sqlserver")
    import pymssql

    def erro(numero):
        return pymssql.OperationalError(numero, b"mensagem qualquer")

    assert d.erro_readonly(erro(262)) is True  # CREATE TABLE permission denied
    assert d.erro_readonly(erro(3906)) is True  # database is read-only
    assert d.erro_readonly(erro(229)) is False  # GENÉRICO — não pode contar
    assert d.erro_readonly(ValueError("nada a ver")) is False
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_dialetos.py::test_sqlserver_erro_readonly_nao_casa_229 -q`
Expected: FAIL com `AttributeError: 'DialetoSqlServer' object has no attribute 'erro_readonly'`.

- [ ] **Step 3: Implementar**

Em `src/db_mcp/dialetos/sqlserver.py`, junto às outras constantes do topo:

```python
# Escrita recusada, MEDIDO no SQL Server 2022 / pymssql 2.3.13:
#   262  — CREATE TABLE permission denied in database
#   3906 — Failed to update database because it is read-only
#
# ⚠️ O 229 (permission denied on the object) fica DE FORA de propósito: é genérico e
# também sobe por falta de SELECT. Casá-lo faria o doctor confirmar "somente-leitura"
# para conexão que falhou por outro motivo — e aqui o GRANT é o ÚNICO cadeado.
NUMEROS_READONLY = frozenset({262, 3906})
```

e os métodos:

```python
    def probar_escrita(self, conn: Any) -> None:
        cur = conn.cursor()
        try:
            cur.execute(self.sql_probe_escrita())
            # Chegou aqui = a escrita PASSOU (usuário mal configurado). Limpa o resíduo;
            # best-effort, porque o diagnóstico ruim já é o que importa.
            with suppress(Exception):
                cur.execute("DROP TABLE __doctor_write_probe__")
        finally:
            cur.close()

    def _numero(self, e: Exception) -> int | None:
        """Número do erro DB-Lib. O pymssql o entrega em `e.args[0]`."""
        args = getattr(e, "args", ())
        return args[0] if args and isinstance(args[0], int) else None

    def erro_readonly(self, e: Exception) -> bool:
        return isinstance(e, self._pymssql.Error) and self._numero(e) in NUMEROS_READONLY

    def erro_do_banco(self, e: Exception) -> bool:
        return isinstance(e, self._pymssql.Error)

    def sql_probe_escrita(self) -> str:
        # CREATE TABLE, não INSERT: o CREATE dá 262 (inequívoco), o INSERT dá 229
        # (genérico). Ver NUMEROS_READONLY.
        return "CREATE TABLE __doctor_write_probe__ (n int)"
```

Adicione `from contextlib import contextmanager, suppress` ao import existente.

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/test_dialetos.py -q`
Expected: PASS.

- [ ] **Step 5: Implementar `erro_de_timeout` — 🪤 o número não está onde parece**

MEDIDO (pymssql 2.3.13 / SQL Server 2022), com `timeout=2` e `WAITFOR DELAY '00:00:10'`:

```
tipo : OperationalError
args : (20047, b'DB-Lib error message 20003, severity 6:\n'
                b'Adaptive Server connection timed out\n'
                b'DB-Lib error message 20047, severity 9:\n'
                b'DBPROCESS is dead or not enabled\n')
```

**`args[0]` é `20047` ("DBPROCESS is dead"), NÃO `20003` ("connection timed out").** O número
que identifica o timeout está *dentro do texto* da mensagem. Quem escrever `20003` na constante
faz um predicado que **nunca casa** — e o timeout vira `ErroBanco` genérico em silêncio.

E `20047` sozinho **não basta**: ele é levantado para qualquer conexão morta (queda de rede
também). Casá-lo puro classificaria falha de rede como timeout. Por isso o predicado exige
**os dois**: o número genérico da exceção **e** a marca do 20003 na mensagem.

Acrescente às constantes:

```python
# Timeout de query, MEDIDO (pymssql 2.3.13 / SQL Server 2022):
#   args[0] = 20047  "DBPROCESS is dead or not enabled"   <- genérico, qualquer conexão morta
#   texto   = 20003  "Adaptive Server connection timed out" <- o que realmente identifica
# O número do timeout NÃO chega em args[0]. Escrever 20003 na constante faria um predicado
# que nunca casa; casar só 20047 classificaria queda de rede como timeout. Exigimos os dois.
NUMERO_CONEXAO_MORTA = 20047
MARCA_TIMEOUT = b"20003"
```

e o método:

```python
    def erro_de_timeout(self, e: Exception) -> bool:
        if not isinstance(e, self._pymssql.Error) or self._numero(e) != NUMERO_CONEXAO_MORTA:
            return False
        args = getattr(e, "args", ())
        texto = args[1] if len(args) > 1 else b""
        if isinstance(texto, str):
            texto = texto.encode("utf-8", "replace")
        return MARCA_TIMEOUT in texto
```

- [ ] **Step 5b: Testar o predicado**

Acrescente a `tests/test_dialetos.py`:

```python
def test_sqlserver_timeout_exige_a_marca_20003():
    """🪤 O número do timeout não chega em args[0].

    MEDIDO: pymssql levanta OperationalError(20047, b'...20003...Adaptive Server connection
    timed out...DBPROCESS is dead...'). O 20047 é genérico (qualquer conexão morta), e o
    20003 — que identifica o timeout — só aparece no texto. Casar 20003 em args[0] daria um
    predicado que nunca casa; casar 20047 puro classificaria queda de rede como timeout.
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
```

Run: `uv run pytest tests/test_dialetos.py -q -k sqlserver`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/db_mcp/dialetos/sqlserver.py tests/test_dialetos.py
git commit -m "feat(sqlserver): erro_readonly casa 262 e nunca 229 + probe de escrita (T4)"
```

---

### Task 5: Cursor, amostra, identidade e introspecção

**Files:**
- Modify: `src/db_mcp/dialetos/sqlserver.py`
- Test: `tests/test_dialetos.py`

- [ ] **Step 1: Escrever os testes que falham**

Acrescente a `tests/test_dialetos.py`:

```python
def test_sqlserver_sql_amostra_usa_top_e_colchetes():
    # T-SQL não tem LIMIT — o sqlglot emite TOP. identify=True cita com COLCHETES,
    # que é o que faz nome reservado (Order -> [Order]) funcionar sem regex.
    sql = dialeto_ou_skip("sqlserver").sql_amostra("clientes", 5)
    assert sql == "SELECT TOP 5 * FROM [clientes]"


def test_sqlserver_sql_identidade_nomeia_usuario_e_banco():
    # MEDIDO: current_database() do Postgres é database() no MySQL e DB_NAME() aqui.
    # Os apelidos são o contrato que mantém a chave do dict igual entre dialetos.
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_dialetos.py -q -k sqlserver`
Expected: FAIL — os métodos não existem.

- [ ] **Step 3: Implementar**

Acrescente ao topo do arquivo:

```python
import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from ..errors import SqlInvalido
```

e os métodos em `DialetoSqlServer`:

```python
    @contextmanager
    def linhas_como_dict(self, conn: Any) -> Iterator[Any]:
        cur = conn.cursor(as_dict=True)
        try:
            yield cur
        finally:
            cur.close()

    def sql_amostra(self, tabela: str, n: int) -> str:
        # SqlglotError (não ParseError): o tokenizer levanta TokenError, que é IRMÃ e não
        # filha — deixar vazar seria recusa sem auditoria (mesmo bug corrigido no 74aba49).
        try:
            tab = sqlglot.parse_one(tabela, into=exp.Table, read=self.sqlglot_dialeto)
        except SqlglotError as e:
            raise SqlInvalido(f"nome de tabela inválido: {tabela!r}") from e
        nome = tab.sql(dialect=self.sqlglot_dialeto, identify=True)
        return f"SELECT TOP {n} * FROM {nome}"

    def sql_identidade(self) -> str:
        # MEDIDO contra SQL Server 2022: devolve ('sa', 'master').
        return "SELECT SUSER_SNAME() AS usuario, DB_NAME() AS banco"

    def sql_introspecao(
        self, tipo: str, schema: str | None = None, tabela: str | None = None
    ) -> tuple[str, tuple[Any, ...]]:
        # Diferente do MySQL: aqui schema é schema DE VERDADE (dbo, etc.) dentro do
        # database, então information_schema.schemata é seguro — lista os schemas do
        # banco corrente, não os bancos da instância.
        if tipo == "schemas":
            return (
                "SELECT schema_name AS schema_name FROM information_schema.schemata "
                "ORDER BY schema_name",
                (),
            )
        if tipo == "tabelas":
            return (
                "SELECT table_name AS table_name FROM information_schema.tables "
                "WHERE table_schema = %s AND table_type = 'BASE TABLE' "
                "ORDER BY table_name",
                (schema,),
            )
        if tipo == "views":
            return (
                "SELECT table_name AS table_name FROM information_schema.views "
                "WHERE table_schema = %s ORDER BY table_name",
                (schema,),
            )
        if tipo == "colunas":
            return (
                "SELECT column_name AS column_name, data_type AS data_type, "
                "is_nullable AS is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s "
                "ORDER BY ordinal_position",
                (schema, tabela),
            )
        raise SqlInvalido(f"tipo de introspecção desconhecido: {tipo!r}")
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
Expected: tudo verde. Contagem sem banco sobe de 197 para ~215.

- [ ] **Step 5: Commit**

```bash
git add src/db_mcp/dialetos/sqlserver.py tests/test_dialetos.py
git commit -m "feat(sqlserver): cursor-dict, amostra com TOP, identidade e introspeccao (T5)"
```

---

### Task 6: Demo — container, seed e o usuário read-only com os DENY

**Files:**
- Create: `demo/init-sqlserver/01-schema.sql`, `02-seed.sql`, `03-mcp-ro.sql`
- Create: `demo/init-sqlserver/entrypoint.sh`
- Modify: `docker-compose.yml`
- Create: `.env.demo-sqlserver`

> ⚠️ A imagem do SQL Server **não** roda `.sql` de um diretório de init como Postgres/MySQL.
> É preciso um entrypoint que sobe o servidor e roda os scripts quando ele aceitar conexão.

- [ ] **Step 1: Escrever o schema**

`demo/init-sqlserver/01-schema.sql`:

```sql
IF DB_ID('demo') IS NULL CREATE DATABASE demo;
GO
USE demo;
GO
IF OBJECT_ID('dbo.clientes') IS NULL
    CREATE TABLE dbo.clientes (id INT PRIMARY KEY, nome NVARCHAR(100), email NVARCHAR(200));
IF OBJECT_ID('dbo.pedidos') IS NULL
    CREATE TABLE dbo.pedidos (id INT PRIMARY KEY, cliente_id INT, valor DECIMAL(10,2));
GO
```

- [ ] **Step 2: Escrever o seed**

`demo/init-sqlserver/02-seed.sql`:

```sql
USE demo;
GO
IF NOT EXISTS (SELECT 1 FROM dbo.clientes)
    INSERT INTO dbo.clientes (id, nome, email) VALUES
        (1, 'Ana Souza',     'ana@exemplo.test'),
        (2, 'Bruno Lima',    'bruno@exemplo.test'),
        (3, 'Carla Dias',    'carla@exemplo.test'),
        (4, 'Diego Alves',   'diego@exemplo.test'),
        (5, 'Elena Ferraz',  'elena@exemplo.test'),
        (6, 'Fabio Nunes',   'fabio@exemplo.test');
IF NOT EXISTS (SELECT 1 FROM dbo.pedidos)
    INSERT INTO dbo.pedidos (id, cliente_id, valor) VALUES
        (1, 1, 150.00), (2, 1, 90.50), (3, 2, 320.00), (4, 3, 45.90);
GO
```

- [ ] **Step 3: Escrever o usuário read-only COM os DENY**

`demo/init-sqlserver/03-mcp-ro.sql`:

```sql
-- Credenciais FAKE e públicas, parte do exemplo. Não são segredo.
--
-- 🚨 Os DENY não são enfeite. MEDIDO no SQL Server 2022: sem eles, um login com
-- GRANT SELECT em UMA tabela ainda enxerga a lista de TODOS os bancos da instância
-- (sys.databases, 6 linhas), TODOS os logins SQL (sys.sql_logins) e o catálogo do
-- master (master.sys.objects). Não é dado de usuário, mas é reconhecimento de terreno
-- de graça — e NÃO tem equivalente no Postgres/MySQL.
--
-- Com os DENY abaixo: master.sys.objects cai de 3 para 0 linhas e sys.databases de 6
-- para 3 (master/tempdb/o próprio — piso do produto, não dá para zerar).
USE master;
GO
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = 'mcp_ro')
    CREATE LOGIN mcp_ro WITH PASSWORD = 'Mcp_ro_demo_2026!', CHECK_POLICY = OFF;
GO
DENY VIEW ANY DATABASE TO mcp_ro;
DENY VIEW ANY DEFINITION TO mcp_ro;
GO
USE demo;
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'mcp_ro')
    CREATE USER mcp_ro FOR LOGIN mcp_ro;
GO
-- Só SELECT, tabela a tabela. Nenhum db_datareader amplo.
GRANT SELECT ON dbo.clientes TO mcp_ro;
GRANT SELECT ON dbo.pedidos  TO mcp_ro;
GO
```

- [ ] **Step 4: Escrever o entrypoint**

`demo/init-sqlserver/entrypoint.sh`:

```bash
#!/bin/bash
set -e
/opt/mssql/bin/sqlservr &
PID=$!
echo "aguardando o SQL Server aceitar conexao..."
for i in {1..60}; do
  if /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -C -Q "SELECT 1" >/dev/null 2>&1; then
    echo "pronto apos ${i}s"
    for f in /init/*.sql; do
      echo "aplicando $f"
      /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -C -i "$f"
    done
    break
  fi
  sleep 1
done
wait $PID
```

Run: `chmod +x demo/init-sqlserver/entrypoint.sh`

- [ ] **Step 5: Acrescentar o serviço ao compose**

Em `docker-compose.yml`, espelhando o serviço do MySQL:

```yaml
  sqlserver:
    image: mcr.microsoft.com/mssql/server:2022-latest
    container_name: db-mcp-demo-sqlserver
    profiles: ["sqlserver"]
    environment:
      ACCEPT_EULA: "Y"
      MSSQL_SA_PASSWORD: "Sonda_MCP_2026!"
      MSSQL_PID: "Developer"
    ports:
      - "1434:1433"   # 1433 costuma estar ocupada por instancia local
    volumes:
      - ./demo/init-sqlserver:/init:ro
    entrypoint: ["/bin/bash", "/init/entrypoint.sh"]
    healthcheck:
      test: ["CMD-SHELL", "/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P \"$$MSSQL_SA_PASSWORD\" -C -Q 'SELECT 1' || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 10
```

- [ ] **Step 6: Escrever o `.env.demo-sqlserver`**

```env
DIALETO=sqlserver
DB_HOST=127.0.0.1
DB_PORT=1434
DB_DBNAME=demo
DB_USER=mcp_ro
DB_PASSWORD=Mcp_ro_demo_2026!
ALLOWLIST=*
```

- [ ] **Step 7: Subir e rodar o doctor**

```bash
docker compose --profile sqlserver up -d
sleep 30
uv run db-mcp --env .env.demo-sqlserver doctor
```

Expected: **6 ok · 0 falha(s)**, com "Somente-leitura confirmado — write recusado: 262".

Se o doctor falhar, **conserte antes de commitar** — este é o critério da fase.

- [ ] **Step 8: Rodar a suíte contra o SQL Server**

```bash
DIALETO=sqlserver DB_HOST=127.0.0.1 DB_PORT=1434 DB_DBNAME=demo DB_USER=mcp_ro \
  DB_PASSWORD='Mcp_ro_demo_2026!' uv run pytest -q -rs
```

Expected: verde, com os skips sendo o corpus de ataque dos *outros* dialetos.

- [ ] **Step 9: Commit**

```bash
git add demo/init-sqlserver docker-compose.yml .env.demo-sqlserver
git commit -m "feat(demo): SQL Server na 1434 com mcp_ro e os DENY medidos (T6)"
```

---

### Task 7: CI com os três bancos

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Acrescentar o job**

Copie o bloco de `integration-mysql` e adapte. Pontos que **não** podem ser esquecidos:

```yaml
  integration-sqlserver:
    runs-on: ubuntu-latest
    services:
      sqlserver:
        image: mcr.microsoft.com/mssql/server:2022-latest
        env:
          ACCEPT_EULA: "Y"
          MSSQL_SA_PASSWORD: "Sonda_MCP_2026!"
          MSSQL_PID: Developer
        ports:
          - 1434:1433
        options: >-
          --health-cmd "/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P Sonda_MCP_2026! -C -Q 'SELECT 1' || exit 1"
          --health-interval 10s --health-timeout 5s --health-retries 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      # --all-extras e OBRIGATORIO: sem o driver o mypy nao resolve o import E o
      # test_invariante_todo_dialeto[sqlserver] se PULA, silenciando o gate.
      - run: uv sync --locked --all-extras
      - name: Seed database
        run: |
          for f in demo/init-sqlserver/*.sql; do
            docker exec "${{ job.services.sqlserver.id }}" \
              /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P 'Sonda_MCP_2026!' -C -i /dev/stdin < "$f"
          done
      - name: Run full test suite
        env:
          DIALETO: sqlserver
          DB_HOST: 127.0.0.1
          DB_PORT: "1434"
          DB_DBNAME: demo
          DB_USER: mcp_ro
          DB_PASSWORD: "Mcp_ro_demo_2026!"
        run: uv run pytest -q -rs
      - name: Doctor (6/6 contra o SQL Server real)
        run: uv run db-mcp --env .env.demo-sqlserver doctor
```

- [ ] **Step 2: Commit e verificar no GitHub**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: job de integracao SQL Server (T7)"
git push
gh run watch $(gh run list --limit 1 --json databaseId -q '.[0].databaseId') --exit-status
```

Expected: **9 jobs verdes** (os 7 de hoje + `integration-sqlserver`).
Se o seed falhar no Actions, ajuste o passo — **não** desabilite o job.

---

### Task 8: Documentação honesta

**Files:**
- Modify: `README.md`, `docs/02-preparar-o-banco.md`, `docs/00-para-leigos.md`,
  `CHANGELOG.md`, `CLAUDE.md`

- [ ] **Step 1: Preencher a coluna do SQL Server na tabela dos cadeados**

A tabela existe no `README.md`, em `docs/02-preparar-o-banco.md` e no `CLAUDE.md`. A coluna
do SQL Server, com o que foi **medido**:

| | SQL Server |
|---|---|
| Cadeado nº 1 | **só `GRANT`/`DENY`** — não existe read-only de sessão (`SET TRANSACTION READ ONLY` → erro 156) |
| Quem garante o read-only | **o GRANT, e só ele** |
| Reset de sessão | **não existe** — por isso o dialeto abre conexão nova por consulta |
| Erro do probe | `262` (CREATE TABLE denied) |
| Força real | **só suspensório** |

- [ ] **Step 2: Escrever a receita de preparação em `docs/02-preparar-o-banco.md`**

Inclua o conteúdo do `03-mcp-ro.sql` (Task 6, Step 3) como receita, **com a explicação dos
DENY** — a medição de que sem eles o login enxerga todos os bancos e todos os logins. Escreva
como **instrução**, não como nota de rodapé.

- [ ] **Step 3: CHANGELOG**

Entrada `## [0.5.0]` descrevendo: dialeto SQL Server, conexão sem pool e por quê, `erro_readonly`
recusando o 229, corpus de ataque, demo e CI. Bump em `pyproject.toml` para `0.5.0`.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/ CHANGELOG.md CLAUDE.md pyproject.toml
git commit -m "docs: cadeados do SQL Server + receita de DENY + 0.5.0 (T8)"
```

---

### Task 9: Verificação final

- [ ] **Step 1: Recriar os containers do zero**

```bash
docker compose --profile mysql --profile sqlserver down -v
docker compose --profile mysql --profile sqlserver up -d
sleep 45
```

- [ ] **Step 2: Rodar os três doctors**

```bash
uv run db-mcp --env .env.demo doctor
uv run db-mcp --env .env.demo-mysql doctor
uv run db-mcp --env .env.demo-sqlserver doctor
```

Expected: **6/6 nos três**.

- [ ] **Step 3: Rodar as quatro suítes e o lint**

```bash
uv run pytest -q
DB_HOST=localhost DB_PORT=5433 DB_DBNAME=demo DB_USER=mcp_ro DB_PASSWORD=mcp_ro_demo uv run pytest -q -rs
DIALETO=mysql DB_HOST=127.0.0.1 DB_PORT=3307 DB_DBNAME=demo DB_USER=mcp_ro DB_PASSWORD=mcp_ro_demo uv run pytest -q -rs
DIALETO=sqlserver DB_HOST=127.0.0.1 DB_PORT=1434 DB_DBNAME=demo DB_USER=mcp_ro DB_PASSWORD='Mcp_ro_demo_2026!' uv run pytest -q -rs
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

Expected: verde em tudo. **Audite os skips** (`-rs`): devem ser só o corpus de ataque dos
outros dialetos.

- [ ] **Step 4: Provar que o núcleo continua agnóstico**

```bash
grep -nE "psycopg|mysql|pymssql" src/db_mcp/dialetos/base.py src/db_mcp/db.py \
  src/db_mcp/server.py src/db_mcp/doctor.py
```

Expected: **nenhuma saída.** Se houver, o dialeto vazou para o núcleo — conserte.

- [ ] **Step 5: Registrar os resultados MEDIDOS no fim deste plano e commitar**

```bash
git add docs/superpowers/plans/2026-07-21-db-mcp-fase-2-sqlserver.md CLAUDE.md
git commit -m "docs(plano): Fase 2 verificada e fechada (T9)"
```

- [ ] **Step 6: Derrubar os containers**

```bash
docker compose --profile mysql --profile sqlserver down -v
```

---

## Definição de pronto

- [ ] `doctor` 6/6 nos **três** bancos
- [ ] Suíte verde nos quatro modos, skips auditados
- [ ] `test_invariante_todo_dialeto[sqlserver]` passando
- [ ] Regressão exigindo recusa de `OPENROWSET`/`WAITFOR`/`EXECUTE AS`/`GO`
- [ ] Regressão exigindo que `erro_readonly` **não** case `229`
- [ ] `ruff` · `ruff format` · `mypy src` limpos
- [ ] CI verde com os **três** jobs de integração
- [ ] Núcleo sem import de driver (Step 4 da Task 9)
- [ ] Tabela dos cadeados preenchida com o medido, sem maquiagem

---

## ✅ Resultados MEDIDOS na verificação final (T9, 2026-07-21)

Containers **recriados do zero** (`down -v` antes) — os três ficaram healthy em ~20 s; o seed do
SQL Server aplicou os 3 `.sql` 2 s após o servidor aceitar conexão.

| | sem banco | Postgres | MySQL | SQL Server |
|---|---|---|---|---|
| suíte | **237** ✅ / 38 ⏭️ | **261** ✅ / 14 ⏭️ | **262** ✅ / 13 ⏭️ | **248** ✅ / 27 ⏭️ |
| `doctor` | — | **6/6** | **6/6** | **6/6** |
| recusa de escrita | — | `25006 ReadOnlySqlTransaction` | `42000 ProgrammingError` | **`262 OperationalError`** |
| latência `SELECT 1` | — | 0,4 ms | 0,7 ms | 1,6 ms |

`ruff check` · `ruff format --check` · `mypy src` **limpos**. CI **8/8** verde
(`integration sqlserver` em **47 s** — o 2º job mais rápido, contra 1m13s do MySQL).

**Skips auditados** (`-rs`, modo SQL Server): 12 do corpus do Postgres + 13 do MySQL + 2 de
integração específica = **27**, e nada mais.

**Núcleo dialeto-agnóstico — provado por EXECUÇÃO, não por inspeção.** Com `psycopg`,
`psycopg_pool`, `mysql`, `mysql.connector`, `pymssql` e `_mssql` forçados a `None` em
`sys.modules`, os **8 módulos do núcleo** importam sem erro:

```
db_mcp.dialetos.base · db_mcp.db · db_mcp.server · db_mcp.doctor
db_mcp.config · db_mcp.cli · db_mcp.guardrails.sql · db_mcp.guardrails.policy
```

(O `grep` por `psycopg|mysql|pymssql` casa comentários — por isso a prova é por execução.)

### O que a fase custou de verdade

| | previsto no plano | real |
|---|---|---|
| tasks | 9 | 9 + **3 correções pós-revisão** (T1b, T2b, T3b) |
| arquivos do dialeto | 1 + 1 linha | ✅ confirmado |
| **arquivos do núcleo** | **0** | 🪤 **2** — `doctor.py` (+16) e `guardrails/policy.py` (+12) |

### Os achados que só o banco vivo entregou

1. 🔴 **`injetar_limit` devolvia SQL cru** no fast-path. O sqlglot faz parse **leniente** e aceita
   `LIMIT n` com `read="tsql"`, então query com `LIMIT` passava intocada e o servidor recusava.
2. **`SELECT 1` sem alias** estoura o cursor `as_dict` do pymssql (`ColumnsWithoutNamesError`).
3. **pymssql não expõe `.sqlstate`** — o número `262` sumia da mensagem do doctor.
4. 🔴 **`timeout=0` no pymssql = SEM timeout**, e a config não tem mínimo (regressão em T3b).
5. **7 entradas `xp_*` da blocklist são inertes** — o motor recusa a sintaxe mesmo para `sa`.
6. **`openrowset` não tinha teste** que provasse o caminho até a blocklist.
7. **`__version__` ficou em `0.4.0`** com o `pyproject` em `0.5.0`, sem nada guardando.

**Nenhum deles apareceria em plano, revisão de código ou teste com mock.**
