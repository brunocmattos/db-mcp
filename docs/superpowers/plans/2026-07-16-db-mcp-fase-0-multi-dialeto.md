# db-mcp Fase 0 — refatorar para multi-dialeto (só PostgreSQL) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar o `pg-readonly-mcp` em `db-mcp` — mesmo comportamento, mas com o contrato `Dialeto` extraído e os defeitos que só apareceriam no SQL Server já corrigidos — sem adicionar nenhum dialeto novo.

**Architecture:** Um repo, um pacote (`db_mcp`), dialetos como módulos em `db_mcp/dialetos/`. Nesta fase existe **um único** dialeto (`postgres`), que reimplementa exatamente o que hoje está espalhado em `db.py`, `server.py` e `guardrails/`. O núcleo (`server.py`, `ratelimit.py`, `observability.py`, `errors.py`) não passa a saber qual banco está do outro lado.

**Tech Stack:** Python 3.11+, uv, FastMCP, psycopg3 + psycopg_pool, sqlglot, pydantic-settings, pytest, ruff, mypy strict.

**Spec:** `docs/superpowers/specs/2026-07-16-db-mcp-multi-dialeto-design.md` (commits `ae01761`, `4f0be50`).

**A prova de que esta fase não quebrou nada:** os mesmos **119 testes verdes** e o `doctor` **6/6** contra o container de demo. Nenhuma funcionalidade nova.

### Sobre as contagens de teste

A linha de base, medida em 2026-07-16: **110 passed, 9 skipped** sem banco, e **119 passed, 0 skipped** com o container de demo de pé (os 9 pulados são os de integração, que destravam com `PG_HOST` no ambiente).

Cada task diz quantos testes **acrescenta**, não o total acumulado. Total absoluto em plano é frágil: a Task 9 **remove** os testes de `_validar_ident` (a função deixa de existir), então qualquer número que eu chutasse aqui estaria errado na hora da verdade. A regra que vale em toda task:

> **Zero vermelho. O total só sobe, exceto na Task 9, que remove os testes da função que ela apaga.**

Se um teste que passava passar a falhar, **pare** — a refatoração mudou comportamento, e o objetivo da fase é justamente não mudar.

---

## Por que Fase 0 existe

Refatoração e dialeto novo juntos = quando quebrar, não se sabe qual dos dois quebrou. Esta fase move o código para a forma certa **com o comportamento congelado**, e usa a suite existente como rede. É a fase que dá vontade de pular e é exatamente a que protege o que já funciona.

## Escopo dos defeitos nesta fase

Os defeitos 5.1–5.3 do spec só **se manifestam** no SQL Server (Fase 2). Aqui a gente conserta a **estrutura** (a costura), não o comportamento de um dialeto que ainda não existe:

| Defeito | O que a Fase 0 faz | O que fica pra Fase 2 |
|---|---|---|
| 5.1 `injetar_limit` com dialeto hardcoded | passa a receber o dialeto; testável já com `"tsql"` porque o sqlglot suporta o dialeto nativamente, sem precisar do nosso módulo | nada |
| 5.2 `amostra` monta `LIMIT` na mão | vira `sql_amostra` no contrato `Dialeto`; a impl `postgres` devolve `LIMIT n` | a impl `sqlserver` devolve `TOP n` |
| 5.3 `_validar_ident` regex de Postgres | introspecção passa a usar **query parameters**; `amostra` passa a citar o identificador via sqlglot | nada |

### Adiado de propósito (do §9 do spec)

O spec pede **teste de regressão de parser** para os casos que hoje falham fechado por `ParseError` (`SELECT ... INTO OUTFILE` no MySQL, `WAITFOR DELAY` no T-SQL) — a ideia é que um upgrade do sqlglot que passe a parseá-los acenda uma luz vermelha em vez de abrir o buraco em silêncio.

**Não entra na Fase 0**, e a omissão é consciente: esses dialetos ainda não existem aqui, então não há buraco a abrir. O teste nasce junto do dialeto que ele protege — `INTO OUTFILE` na Fase 1, `WAITFOR DELAY` na Fase 2. Escrever agora seria testar um caminho de código inexistente.

## Correção ao spec (§5.3)

O spec descreve 5.3 como um problema só. São **dois**, em posições SQL diferentes:

- **Introspecção** (`listar_tabelas`, `listar_views`, `descrever_tabela`): o nome entra como **literal de string** — `WHERE table_schema = '{schema}'`. Aqui `Order` e `2fa_tokens` são literais perfeitamente válidos; a regex é só restritiva demais. A correção certa não é relaxar a regex, é usar **query parameters** — que mata a classe de injeção inteira em vez de filtrá-la. O `doctor.py:270` já faz assim (`unnest(%s::text[], %s::text[])`); o `server.py` é que não faz.
- **`amostra`**: o nome entra como **identificador** — `FROM {tabela}`. Aqui sim `Order` precisa virar `[Order]` no T-SQL e `2fa_tokens` precisa de crases no MySQL. Correção: citar via sqlglot.

Os três drivers do projeto usam `paramstyle = "pyformat"` (`%s`): psycopg3, mysql-connector-python e pymssql. Ou seja, parâmetros são neutros de dialeto. **Verificar essa afirmação na Fase 1 e 2** antes de confiar nela.

## Divergências deste plano em relação ao spec (§3)

O spec listou o contrato `Dialeto` antes de eu escrever o código passo a passo. Ao detalhar, três membros mudaram. Registrado aqui porque divergência silenciosa entre spec e plano é como spec vira ficção.

| Membro no spec | Neste plano | Por quê |
|---|---|---|
| `configurar(conn)` e `resetar(conn)` | **saem do contrato**; viram `_configurar`/`_resetar` privados de `DialetoPostgres`, passados como callback pro `ConnectionPool` | São detalhe de implementação do pool do psycopg, não do contrato. O pool do mysql-connector e o pymssql têm mecanismos de hook diferentes — forçar essa forma no contrato engessaria os dialetos que ainda nem existem. Quem garante o reset é o `criar_pool` de cada dialeto. |
| `sql_introspecao(tipo, **kw)` | **adiado pra Fase 1**; nesta fase o SQL de introspecção fica em `server.py` | Postgres é o único dialeto. Mover agora seria especulação: a forma certa depende de como a semântica `schema == database` do MySQL se resolver (spec §6), e isso só se descobre na Fase 1. YAGNI. |
| — | **entram** `erro_de_timeout(e)`, `erro_do_banco(e)`, `linhas_como_dict(conn)` | O `db.py` precisa traduzir exceção de driver em erro tratado e obter linhas como dict. As duas coisas são específicas do driver e o spec não tinha percebido. Sem elas, `db.py` continuaria importando `psycopg` — ou seja, não teria dialeto nenhum. |

Contagem final: onze membros, como no spec, mas não os mesmos onze.

---

## Estrutura de arquivos

```
src/db_mcp/                        (era src/pg_readonly_mcp/)
├── __init__.py                    modificar: __version__ = "0.3.0"
├── cli.py                         modificar: --dialect
├── config.py                      modificar: campo `dialeto`
├── db.py                          modificar: fachada fina, delega ao dialeto
├── doctor.py                      modificar: probe de escrita delega
├── errors.py                      inalterado
├── observability.py               inalterado
├── py.typed                       inalterado
├── server.py                      modificar: params na introspecção; sql_amostra
├── guardrails/
│   ├── __init__.py                inalterado
│   ├── policy.py                  modificar: injetar_limit recebe dialeto
│   ├── ratelimit.py               inalterado
│   └── sql.py                     modificar: validar(sql, dialeto, perfil)
└── dialetos/                      CRIAR
    ├── __init__.py                CRIAR: obter_dialeto()
    ├── base.py                    CRIAR: o Protocol + Perfil
    └── postgres.py                CRIAR: a única impl desta fase

tests/
├── test_dialetos.py               CRIAR
├── test_ataques_e2e.py            CRIAR (teste de fiação)
└── (os 12 existentes)             modificar: imports + assinaturas
```

**Responsabilidade de cada arquivo novo:**
- `dialetos/base.py`: o contrato e nada mais. Sem I/O, sem import de driver.
- `dialetos/postgres.py`: tudo o que é específico de PostgreSQL, incluindo o import do psycopg.
- `dialetos/__init__.py`: só o `obter_dialeto(nome)`, que importa o módulo do dialeto **lazy** (senão instalar o extra `postgres` viraria obrigatório pra quem só usa MySQL, nas fases seguintes).

---

## Task 1: Preparar o terreno (pasta, remote, container)

**Files:**
- Modify: `.git/config` (via `git remote set-url`)
- Rename: a pasta do clone

O repo já foi renomeado no GitHub para `db-mcp` (a URL antiga redireciona, por isso o clone atual ainda funciona). O clone local ainda se chama `pg-readonly-mcp` e aponta pro remote velho.

- [ ] **Step 1: Derrubar o container de demo ANTES de renomear a pasta**

O nome do projeto do compose vem do nome do diretório. Se renomear a pasta com o container de pé, o projeto vira órfão e `docker compose down` não o acha mais.

```bash
cd "C:/Users/bruno.outcore/Documents/Programação/pg-readonly-mcp"
docker compose down -v
```
Expected: `Container pg-readonly-mcp-demo Removed` e `Network pg-readonly-mcp_default Removed`.

- [ ] **Step 2: Renomear a pasta**

```bash
cd "C:/Users/bruno.outcore/Documents/Programação"
mv pg-readonly-mcp db-mcp
cd db-mcp
```

- [ ] **Step 3: Apontar o remote pro nome novo**

```bash
git remote set-url origin https://github.com/brunocmattos/db-mcp
git remote -v
```
Expected: as duas linhas com `db-mcp`.

- [ ] **Step 4: Recriar o venv (os caminhos absolutos quebraram com o rename)**

```bash
rm -rf .venv
uv sync
```

- [ ] **Step 5: Verificar que a base continua verde antes de mexer em código**

```bash
uv run pytest -q
```
Expected: `110 passed, 9 skipped` (os 9 de integração se pulam sem banco — normal aqui).

- [ ] **Step 6: Commit**

Nada a commitar (rename de pasta e remote não são conteúdo). Seguir.

---

## Task 2: Renomear o pacote e o comando

**Files:**
- Rename: `src/pg_readonly_mcp/` → `src/db_mcp/`
- Modify: `pyproject.toml`, todos os `tests/*.py`, `README.md`, `SETUP.md`, `CHANGELOG.md`, `docs/*.md`, `.claude/skills/setup-pg-readonly-mcp/SKILL.md`, `docker-compose.yml` (comentários), `.github/workflows/ci.yml`

- [ ] **Step 1: Mover o pacote (com git mv, pra preservar o histórico)**

```bash
git mv src/pg_readonly_mcp src/db_mcp
```

- [ ] **Step 2: Trocar os imports no código e nos testes**

```bash
grep -rl "pg_readonly_mcp" src tests | xargs sed -i 's/pg_readonly_mcp/db_mcp/g'
grep -rn "pg_readonly_mcp" src tests || echo "OK: nenhuma ocorrencia restante"
```
Expected: `OK: nenhuma ocorrencia restante`.

- [ ] **Step 3: Atualizar o `pyproject.toml`**

Quatro pontos, todos obrigatórios (esquecer um quebra build, lint ou tipos):

```toml
[project]
name = "db-mcp"
version = "0.3.0"
description = "MCP server that gives read-only access to PostgreSQL, MySQL and SQL Server"

[project.scripts]
db-mcp = "db_mcp.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/db_mcp"]

[tool.ruff.lint.isort]
known-first-party = ["db_mcp"]
```

- [ ] **Step 4: Atualizar o nome do servidor MCP e a versão**

`src/db_mcp/server.py` — o `FastMCP(name=...)` é o nome que o cliente MCP enxerga:

```python
mcp = FastMCP(name="db-mcp", auth=auth)
```

`src/db_mcp/__init__.py`:

```python
__version__ = "0.3.0"
```

- [ ] **Step 5: Consertar os testes que fixam o nome antigo**

`tests/test_cli.py` tem três lugares. O primeiro é uma asserção de verdade; os outros dois são só `argv[0]` cosmético, mas ficam errados se não trocar:

```python
def test_montar_retorna_servidor(monkeypatch):
    for k, v in {"PG_HOST": "h", "PG_DBNAME": "d", "PG_PASSWORD": "p"}.items():
        monkeypatch.setenv(k, v)
    mcp = montar(env_file=None, yaml_file="/nao/existe.yaml", conectar=False)
    assert mcp.name == "db-mcp"
```

```python
    monkeypatch.setattr(sys, "argv", ["db-mcp", "doctor"])
```

```python
    monkeypatch.setattr(
        sys,
        "argv",
        ["db-mcp", "--env", "naoexiste.env", "--config", "naoexiste.yaml", "run"],
    )
```

- [ ] **Step 6: Renomear a skill de setup**

```bash
git mv .claude/skills/setup-pg-readonly-mcp .claude/skills/setup-db-mcp
sed -i 's/setup-pg-readonly-mcp/setup-db-mcp/g; s/pg-readonly-mcp/db-mcp/g' .claude/skills/setup-db-mcp/SKILL.md
```

- [ ] **Step 7: Trocar o nome nos docs e no CI**

```bash
grep -rl "pg-readonly-mcp" README.md SETUP.md CHANGELOG.md docs/ .github/ docker-compose.yml demo/ deployments/ \
  | xargs sed -i 's/pg-readonly-mcp/db-mcp/g'
grep -rn "pg-readonly-mcp" . --exclude-dir=.git --exclude-dir=.venv --exclude-dir=uv.lock || echo "OK: limpo"
```

Atenção: `docs/DESIGN.md` e `docs/00-para-leigos.md` falam de "pg-readonly-mcp" como produto **só-Postgres**. Esta task só troca o **nome**; o conteúdo (os três cadeados, os não-objetivos) é reescrito na Task 12. Não tentar arrumar o texto aqui.

- [ ] **Step 8: Reinstalar (o nome do script mudou) e rodar tudo**

```bash
uv sync
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```
Expected: `110 passed, 9 skipped`, `All checks passed!`, `Success: no issues found`.

- [ ] **Step 9: Verificar que o comando novo existe e o velho não**

```bash
uv run db-mcp --help
```
Expected: usage com `prog: db-mcp`. Ajustar `argparse.ArgumentParser(prog="pg-readonly-mcp")` → `prog="db-mcp"` em `cli.py` se ainda estiver velho.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor!: renomeia pg-readonly-mcp para db-mcp

O repo virou multi-dialeto (spec 2026-07-16). O nome pg- deixaria de fazer
sentido com MySQL e SQL Server entrando nas fases 1 e 2.

BREAKING CHANGE: o comando passa a ser db-mcp e o pacote db_mcp. Quem tinha
o MCP registrado no cliente precisa reapontar."
```

---

## Task 3: Campo `dialeto` na config e flag `--dialect`

**Files:**
- Modify: `src/db_mcp/config.py`, `src/db_mcp/cli.py`
- Test: `tests/test_config.py`, `tests/test_cli.py`

- [ ] **Step 1: Escrever os testes que falham**

Em `tests/test_config.py`:

```python
def test_dialeto_default_e_postgres(monkeypatch):
    for k, v in {"PG_HOST": "h", "PG_DBNAME": "d", "PG_PASSWORD": "p"}.items():
        monkeypatch.setenv(k, v)
    s = Settings.load(env_file=None, yaml_file="/nao/existe.yaml")
    assert s.dialeto == "postgres"


def test_dialeto_invalido_e_recusado_na_subida(monkeypatch):
    # Fail-fast: um dialeto que nao existe nao pode passar da validacao e so
    # explodir la na frente, na hora de conectar.
    for k, v in {"PG_HOST": "h", "PG_DBNAME": "d", "PG_PASSWORD": "p"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("DIALETO", "oracle")
    with pytest.raises(ValidationError):
        Settings.load(env_file=None, yaml_file="/nao/existe.yaml")
```

Garantir os imports no topo do arquivo:

```python
import pytest
from pydantic import ValidationError

from db_mcp.config import Settings
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
uv run pytest tests/test_config.py -k dialeto -v
```
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'dialeto'`.

- [ ] **Step 3: Implementar**

`src/db_mcp/config.py`, dentro de `class Settings`, logo acima de `transport`:

```python
    # --- ajustes (via config.yaml, com env como override) ---
    dialeto: Literal["postgres", "mysql", "sqlserver"] = "postgres"
    transport: Literal["stdio", "http"] = "stdio"
```

`Literal` já está importado no arquivo.

- [ ] **Step 4: Rodar e ver passar**

```bash
uv run pytest tests/test_config.py -k dialeto -v
```
Expected: 2 passed.

- [ ] **Step 5: Adicionar a flag `--dialect` no cli**

`src/db_mcp/cli.py`, dentro de `main()`, junto dos outros argumentos globais:

```python
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--env", default=".env")
    parser.add_argument(
        "--dialect",
        choices=["postgres", "mysql", "sqlserver"],
        default=None,
        help="sobrescreve o dialeto da config",
    )
```

E depois do `Settings.load` do caminho `run`:

```python
    s = Settings.load(env_file=args.env, yaml_file=args.config)
    if args.dialect:
        s.dialeto = args.dialect
    configurar_logging(s.log_level)
```

- [ ] **Step 6: Teste da flag**

Em `tests/test_cli.py`:

```python
def test_flag_dialect_sobrescreve_a_config(monkeypatch):
    for k in ("PG_HOST", "PG_DBNAME", "PG_PASSWORD"):
        monkeypatch.setenv(k, "x")
    visto = {}

    def _captura(s, conectar=True):
        visto["dialeto"] = s.dialeto
        raise SystemExit(0)  # nao sobe servidor de verdade no teste

    monkeypatch.setattr(cli, "construir_servidor", _captura)
    monkeypatch.setattr(
        sys, "argv",
        ["db-mcp", "--env", "naoexiste.env", "--config", "naoexiste.yaml",
         "--dialect", "mysql", "run"],
    )
    with pytest.raises(SystemExit):
        cli.main()
    assert visto["dialeto"] == "mysql"
```

- [ ] **Step 7: Rodar tudo**

```bash
uv run pytest -q
```
Expected: **+3 testes** em relação à base, zero vermelho.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(config): campo dialeto e flag --dialect (default postgres)"
```

---

## Task 4: O contrato `Dialeto` e a implementação `postgres`

**Files:**
- Create: `src/db_mcp/dialetos/__init__.py`, `src/db_mcp/dialetos/base.py`, `src/db_mcp/dialetos/postgres.py`
- Test: `tests/test_dialetos.py`

Esta task **só cria** o contrato e a impl. Ninguém consome ainda (Tasks 5–10 fazem isso, uma peça por vez). O comportamento não muda.

- [ ] **Step 1: Escrever o teste que falha**

`tests/test_dialetos.py`:

```python
import pytest

from db_mcp.dialetos import obter_dialeto
from db_mcp.dialetos.base import Perfil


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
    # a lista e do dialeto, nao global: funcao de OUTRO banco nao entra aqui
    assert "load_file" not in fp  # MySQL
    assert "openquery" not in fp  # T-SQL


def test_sql_amostra_do_postgres_usa_limit_e_cita_o_nome():
    # identify=True cita o identificador ("clientes"): e o que faz o nome reservado
    # (Order -> [Order] no T-SQL) funcionar sem regex. No postgres sai com aspas duplas.
    assert obter_dialeto("postgres").sql_amostra("clientes", 5) == 'SELECT * FROM "clientes" LIMIT 5'


def test_perfil_so_tem_somente_leitura_nesta_fase():
    # A escrita ganha spec proprio. O parametro existe pra costura ficar no lugar
    # certo, mas nesta fase so ha um valor possivel.
    assert [p.name for p in Perfil] == ["SOMENTE_LEITURA"]
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
uv run pytest tests/test_dialetos.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'db_mcp.dialetos'`.

- [ ] **Step 3: Criar `src/db_mcp/dialetos/base.py`**

```python
from __future__ import annotations

from contextlib import AbstractContextManager
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from ..config import Settings


class Perfil(Enum):
    """O que o MCP tem permissao de fazer.

    Existe com um unico valor de proposito: a escrita tem spec proprio (ver
    docs/superpowers/specs/2026-07-16-db-mcp-multi-dialeto-design.md, §1). O
    parametro esta aqui pra costura nascer no lugar certo, nao pra ser usada.

    O principio que vale quando a escrita chegar: a config so pode SUBTRAIR do
    que o usuario do banco ja pode fazer, nunca somar. Perfil de escrita num
    usuario read-only continua nao escrevendo — o banco recusa.
    """

    SOMENTE_LEITURA = "somente_leitura"


class PoolLike(Protocol):
    """O minimo que db.py usa de um pool. psycopg_pool ja tem esta forma."""

    def connection(self) -> Any: ...
    def close(self) -> None: ...


class Dialeto(Protocol):
    """O que muda entre bancos. Tudo o mais e dialeto-agnostico."""

    nome: str
    sqlglot_dialeto: str
    funcs_proibidas: frozenset[str]
    schema_padrao: str
    erros_readonly: tuple[type[Exception], ...]

    def criar_pool(self, s: Settings) -> PoolLike: ...

    def erro_de_timeout(self, e: Exception) -> bool:
        """True se a excecao do driver representa query cortada por timeout."""
        ...

    def erro_do_banco(self, e: Exception) -> bool:
        """True se a excecao veio do driver (vira ErroBanco tratado)."""
        ...

    def linhas_como_dict(self, conn: Any) -> AbstractContextManager[Any]:
        """Cursor que devolve linhas como dict. Usado como `with ... as cur`.

        AbstractContextManager (nao Iterator): a impl usa @contextmanager, que
        devolve um context manager. Declarar Iterator aqui quebra o mypy strict.
        """
        ...

    def sql_amostra(self, tabela: str, n: int) -> str: ...

    def sql_probe_escrita(self) -> str:
        """DDL que o doctor tenta e ESPERA que falhe."""
        ...
```

- [ ] **Step 4: Criar `src/db_mcp/dialetos/postgres.py`**

O conteúdo vem de `db.py` e de `guardrails/sql.py` — é movimento, não invenção. A lista de funções é **exatamente** a `FUNCS_PROIBIDAS` que hoje está em `guardrails/sql.py:35-94`; copiar inteira, sem editar.

```python
from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import sqlglot
from sqlglot import exp

if TYPE_CHECKING:
    from ..config import Settings
    from .base import PoolLike

FUNCS_PROIBIDAS_POSTGRES = frozenset({
    # arquivo / objeto grande / rede
    "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_stat_file",
    "pg_read_server_files", "lo_import", "lo_export", "lo_get", "lo_open",
    "loread", "dblink", "dblink_exec",
    # escreve WAL duravel mesmo em read-only
    "pg_logical_emit_message",
    # outros efeitos colaterais que o read-only do banco nao barra
    "pg_notify", "pg_export_snapshot", "txid_current", "pg_current_xact_id",
    # DoS / controle de sessao alheia
    "pg_sleep", "pg_sleep_for", "pg_sleep_until", "pg_terminate_backend",
    "pg_cancel_backend",
    # efeito colateral em sequence
    "nextval", "setval",
    # muda o estado da sessao (GUC)
    "set_config",
    # advisory locks
    "pg_advisory_lock", "pg_advisory_lock_shared", "pg_advisory_xact_lock",
    "pg_advisory_xact_lock_shared", "pg_try_advisory_lock",
    "pg_try_advisory_lock_shared", "pg_try_advisory_xact_lock",
    "pg_try_advisory_xact_lock_shared", "pg_advisory_unlock",
    "pg_advisory_unlock_shared", "pg_advisory_unlock_all",
    # export XML: recebem tabela/consulta como string e escapam da allowlist
    "query_to_xml", "query_to_xmlschema", "query_to_xml_and_xmlschema",
    "table_to_xml", "table_to_xmlschema", "table_to_xml_and_xmlschema",
    "cursor_to_xml", "cursor_to_xmlschema", "schema_to_xml",
    "schema_to_xmlschema", "schema_to_xml_and_xmlschema", "database_to_xml",
    "database_to_xmlschema", "database_to_xml_and_xmlschema",
})


class DialetoPostgres:
    nome = "postgres"
    sqlglot_dialeto = "postgres"
    funcs_proibidas = FUNCS_PROIBIDAS_POSTGRES
    schema_padrao = "public"

    def __init__(self) -> None:
        import psycopg  # lazy: o extra `postgres` so e exigido de quem usa postgres

        self._psycopg = psycopg
        self.erros_readonly = (
            psycopg.errors.InsufficientPrivilege,   # 42501 — role sem privilegio
            psycopg.errors.ReadOnlySqlTransaction,  # 25006 — transacao READ ONLY
        )

    def criar_pool(self, s: Settings) -> PoolLike:
        import psycopg
        from psycopg_pool import ConnectionPool

        conninfo = psycopg.conninfo.make_conninfo(
            host=s.pg_host, port=s.pg_port, dbname=s.pg_dbname, user=s.pg_user,
            password=s.pg_password, sslmode=s.pg_sslmode,
            application_name="db-mcp",
            options=f"-c statement_timeout={s.statement_timeout_ms} "
            f"-c idle_in_transaction_session_timeout=10000",
        )
        return ConnectionPool(
            conninfo, min_size=s.pool_min, max_size=s.pool_max,
            configure=self._configurar, reset=self._resetar, open=True,
        )

    @staticmethod
    def _configurar(conn: Any) -> None:
        conn.read_only = True  # toda transacao da conexao e READ ONLY
        # Nao deixa o psycopg auto-preparar statements: o DISCARD ALL do reset apaga
        # os prepared no servidor, mas o cache do psycopg continuaria apontando pra
        # eles, e a proxima query identica quebraria.
        conn.prepare_threshold = None

    @staticmethod
    def _resetar(conn: Any) -> None:
        # Zera o estado de sessao (GUCs, advisory locks, temp tables) pra que nada
        # vaze de um cliente pro proximo que reusar a mesma conexao fisica.
        conn.rollback()
        autocommit = conn.autocommit
        conn.autocommit = True  # DISCARD ALL nao roda dentro de uma transacao
        try:
            conn.execute("DISCARD ALL")
        finally:
            conn.autocommit = autocommit
            conn.read_only = True  # DISCARD ALL zera o modo read-only; reaplica

    def erro_de_timeout(self, e: Exception) -> bool:
        return isinstance(e, self._psycopg.errors.QueryCanceled)

    def erro_do_banco(self, e: Exception) -> bool:
        return isinstance(e, self._psycopg.Error)

    @contextmanager
    def linhas_como_dict(self, conn: Any) -> Any:
        from psycopg.rows import dict_row

        with conn.cursor(row_factory=dict_row) as cur:
            yield cur

    def sql_amostra(self, tabela: str, n: int) -> str:
        tab = sqlglot.parse_one(tabela, into=exp.Table, read=self.sqlglot_dialeto)
        return f"SELECT * FROM {tab.sql(dialect=self.sqlglot_dialeto, identify=True)} LIMIT {n}"

    def sql_probe_escrita(self) -> str:
        return "CREATE TABLE __doctor_write_probe__ (n int)"
```

- [ ] **Step 5: Criar `src/db_mcp/dialetos/__init__.py`**

```python
from __future__ import annotations

from .base import Dialeto, Perfil, PoolLike

__all__ = ["Dialeto", "Perfil", "PoolLike", "obter_dialeto"]


def obter_dialeto(nome: str) -> Dialeto:
    """Instancia o dialeto pelo nome. Importa o modulo lazy: o driver de cada banco
    e um extra opcional, e quem usa so um banco nao deve precisar dos outros."""
    if nome == "postgres":
        from .postgres import DialetoPostgres

        return DialetoPostgres()
    raise ValueError(f"dialeto desconhecido: {nome!r}")
```

Nota: `mysql` e `sqlserver` **não** entram aqui nesta fase. O `config.py` aceita os três nomes, mas só `postgres` resolve — e o erro é legível. As Fases 1 e 2 adicionam os ramos.

- [ ] **Step 6: Rodar e ver passar**

```bash
uv run pytest tests/test_dialetos.py -v
```
Expected: 5 passed.

- [ ] **Step 7: Verificar lint e tipos (o Protocol é onde o mypy strict costuma reclamar)**

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```
Expected: tudo limpo. Se o mypy reclamar que `DialetoPostgres` não satisfaz `Dialeto`, o problema é assinatura divergente — corrigir a impl, **não** afrouxar o Protocol.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(dialetos): contrato Dialeto e implementacao postgres

Ninguem consome ainda; as tasks seguintes migram uma peca por vez.
Perfil nasce com um unico valor: a escrita tem spec proprio."
```

---

## Task 5: `db.py` delega ao dialeto

**Files:**
- Modify: `src/db_mcp/db.py`
- Test: `tests/test_db_integration.py` (existente; não deve precisar de mudança)

- [ ] **Step 1: Reescrever `src/db_mcp/db.py`**

Toda a especificidade de psycopg sai daqui e passa a vir do dialeto. A forma pública (`Database(s)`, `.executar(sql, max_rows)`, `.close()`) **não muda** — é o que garante que `server.py` e os testes existentes continuem valendo.

```python
from __future__ import annotations

from typing import Any

from .config import Settings
from .dialetos import Dialeto, obter_dialeto
from .errors import ConsultaTimeout, ErroBanco


class Database:
    def __init__(self, s: Settings, dialeto: Dialeto | None = None) -> None:
        self.dialeto = dialeto if dialeto is not None else obter_dialeto(s.dialeto)
        self.pool = self.dialeto.criar_pool(s)

    def executar(self, sql: str, max_rows: int, params: Any = None) -> tuple[list[dict[str, Any]], bool]:
        """Roda o SQL (ja validado) e devolve (linhas, truncado).

        `params` vai como query parameter do driver — os tres drivers do projeto
        usam paramstyle pyformat (%s). E o que mantem a introspeccao livre de
        injecao sem depender de regex no nome."""
        try:
            with self.pool.connection() as conn, self.dialeto.linhas_como_dict(conn) as cur:
                cur.execute(sql, params)
                linhas = cur.fetchmany(max_rows)
                truncado = cur.fetchone() is not None
            return linhas, truncado
        except Exception as e:
            if self.dialeto.erro_de_timeout(e):
                raise ConsultaTimeout("consulta excedeu o tempo limite") from e
            if self.dialeto.erro_do_banco(e):
                # tabela/coluna inexistente, permissao negada, etc. — vira erro
                # tratado (auditavel e com codigo estavel) em vez de escapar cru.
                raise ErroBanco(f"erro do banco: {e}") from e
            raise
```

- [ ] **Step 2: Rodar a suite inteira (o comportamento não pode ter mudado)**

```bash
uv run pytest -q
```
Expected: **zero teste novo, zero vermelho** — esta task é refatoração pura. Se algo ficou vermelho, o comportamento mudou.

- [ ] **Step 3: Rodar os testes de integração contra o banco vivo**

```bash
docker compose up -d
PG_HOST=localhost PG_PORT=5433 PG_DBNAME=demo PG_USER=mcp_ro PG_PASSWORD=mcp_ro_demo \
  uv run pytest -q
```
Expected: **zero skipped, zero vermelho.** Este passo é o que prova que o pool novo (via dialeto) conecta de verdade — o `pytest` sem banco não exercita `criar_pool`.

- [ ] **Step 4: Tipos**

```bash
uv run mypy src
```
Expected: limpo.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(db): Database delega ao dialeto; executar aceita params"
```

---

## Task 6: `guardrails/sql.py` recebe o dialeto

**Files:**
- Modify: `src/db_mcp/guardrails/sql.py`
- Test: `tests/test_sql.py`

`TAGS_PROIBIDAS` **fica** no módulo: os nomes de nó do sqlglot (`Insert`, `Update`, `Delete`, `Create`, `Drop`, `Into`, `Lock`, ...) são idênticos nos três dialetos — isso foi medido, não presumido (spec §2). O que sai é a lista de **funções**, que vem do dialeto.

- [ ] **Step 1: Trocar a assinatura em `src/db_mcp/guardrails/sql.py`**

Remover o bloco `FUNCS_PROIBIDAS = {...}` inteiro (linhas 33-94) — ele agora vive em `dialetos/postgres.py`. Manter `TAGS_PROIBIDAS` e `_iter_nos`. Trocar a função:

```python
from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from ..errors import SomenteLeitura, SqlInvalido

if TYPE_CHECKING:
    from ..dialetos import Dialeto
    from ..dialetos.base import Perfil

# (TAGS_PROIBIDAS e _iter_nos ficam como estao)


def validar(sql: str, dialeto: Dialeto, perfil: Perfil) -> None:
    """Levanta SqlInvalido/SomenteLeitura se `sql` nao for um unico SELECT seguro.

    `perfil` so tem um valor nesta fase (SOMENTE_LEITURA) — a escrita tem spec
    proprio. O parametro existe pra costura nascer no lugar certo.
    """
    try:
        arvores = [
            a
            for a in sqlglot.parse(
                sql, read=dialeto.sqlglot_dialeto, error_level=sqlglot.ErrorLevel.RAISE
            )
            if a is not None
        ]
    except ParseError as e:
        raise SqlInvalido(f"SQL inválido: {e}") from e

    if len(arvores) != 1:
        raise SqlInvalido("apenas uma instrução SQL é permitida")

    raiz = arvores[0]
    # SetOperation cobre UNION, INTERSECT e EXCEPT — todos só-leitura.
    if not isinstance(raiz, (exp.Select, exp.SetOperation)):
        raise SomenteLeitura("apenas comandos SELECT são permitidos")

    for node in _iter_nos(raiz):
        nome_no = type(node).__name__
        if nome_no in TAGS_PROIBIDAS:
            raise SomenteLeitura(f"comando não permitido: {nome_no}")
        if isinstance(node, exp.Anonymous):
            # node.name devolve o nome nu mesmo com aspas ("pg_read_file") ou schema
            # (pg_catalog.pg_read_file) — str(node.this) traria as aspas e escaparia.
            fn = node.name.lower()
            if fn in dialeto.funcs_proibidas:
                raise SomenteLeitura(f"função não permitida: {fn}")
```

- [ ] **Step 2: Adaptar `tests/test_sql.py` — parametrizando por dialeto**

Esta é a estrutura que as Fases 1 e 2 vão reusar: a tabela de ataques passa a ser **por dialeto**, e cada fase só acrescenta a sua. Trocar o topo do arquivo:

```python
import pytest

from db_mcp.dialetos import obter_dialeto
from db_mcp.dialetos.base import Perfil
from db_mcp.errors import SomenteLeitura, SqlInvalido
from db_mcp.guardrails.sql import validar

PG = obter_dialeto("postgres")


def _validar_pg(sql: str) -> None:
    validar(sql, PG, Perfil.SOMENTE_LEITURA)
```

E trocar **todas** as chamadas `validar_somente_leitura(x)` por `_validar_pg(x)` no arquivo:

```bash
sed -i 's/validar_somente_leitura(/_validar_pg(/g' tests/test_sql.py
```

Cuidado: o `sed` acima também trocaria a linha do import, que já foi reescrita no bloco anterior — conferir com `grep -n "validar_somente_leitura" tests/test_sql.py` e esperar zero ocorrências.

- [ ] **Step 3: Rodar**

```bash
uv run pytest tests/test_sql.py -q
```
Expected: todos passam, mesma contagem de antes (nenhum ataque deixou de ser barrado).

- [ ] **Step 4: Ajustar `server.py` para a assinatura nova**

Em `src/db_mcp/server.py`, no `Nucleo.consultar`:

```python
            validar(sql, self.dialeto, Perfil.SOMENTE_LEITURA)  # cadeado nº 3 (a)
```

E o `Nucleo.__init__` passa a guardar o dialeto:

```python
    def __init__(self, s: Settings, db: Database | None = None) -> None:
        self.s = s
        self.db = db if db is not None else Database(s)
        self.dialeto = self.db.dialeto
        self.rl = RateLimiter(por_minuto=s.rate_limit_per_min)
        self.aud = Auditoria(s.audit_log_path)
```

Trocar o import no topo de `server.py`:

```python
from .dialetos.base import Perfil
from .guardrails.sql import validar
```

- [ ] **Step 5: Rodar tudo**

```bash
uv run pytest -q && uv run ruff check . && uv run mypy src
```
Expected: **zero teste novo, zero vermelho**, lint e tipos limpos. Nenhum ataque pode ter deixado de ser barrado — se `test_sql.py` ficou verde com menos testes, alguém apagou caso de ataque.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(guardrails): validar(sql, dialeto, perfil)

A lista de funcoes proibidas sai do modulo e passa a vir do dialeto.
TAGS_PROIBIDAS fica: os nomes de no do sqlglot sao identicos nos 3
dialetos (medido, spec §2). Testes parametrizados por dialeto — e a
estrutura que as fases 1 e 2 reusam."
```

---

## Task 7: FIX 5.1 — `injetar_limit` recebe o dialeto

**Files:**
- Modify: `src/db_mcp/guardrails/policy.py`
- Test: `tests/test_policy.py`

- [ ] **Step 1: Escrever o teste que falha (a regressão real)**

Em `tests/test_policy.py`:

```python
def test_injetar_limit_emite_no_dialeto_alvo():
    # Regressao 5.1: com dialect="postgres" hardcoded, um TOP acima do teto virava
    # "LIMIT 100" — sintaxe INVALIDA no SQL Server. Testavel ja nesta fase porque o
    # sqlglot suporta tsql nativamente, sem precisar do nosso modulo de dialeto.
    out = injetar_limit("SELECT TOP 9999 * FROM t", 100, "tsql")
    assert "TOP 100" in out.upper()
    assert "LIMIT" not in out.upper()


def test_injetar_limit_no_mysql_usa_limit():
    out = injetar_limit("SELECT * FROM t", 100, "mysql")
    assert "LIMIT 100" in out.upper()


def test_injetar_limit_tsql_respeita_top_dentro_do_teto():
    sql = "SELECT TOP 5 * FROM t"
    assert injetar_limit(sql, 100, "tsql") == sql
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
uv run pytest tests/test_policy.py -k injetar_limit -v
```
Expected: FAIL — `TypeError: injetar_limit() takes 2 positional arguments but 3 were given`.

- [ ] **Step 3: Implementar**

`src/db_mcp/guardrails/policy.py`:

```python
def injetar_limit(sql: str, teto: int, dialeto: str) -> str:
    """Garante que a query não peça mais que `teto` linhas. Se já houver um `LIMIT`/`FETCH`
    literal dentro do teto, respeita sem mexer; qualquer outra forma (sem limite, `LIMIT ALL`,
    limite gigante ou não-literal, `FETCH FIRST n ROWS`) é normalizada pra o teto.

    `dialeto` e o dialeto do sqlglot ("postgres" | "mysql" | "tsql"): o SQL tem que
    sair na sintaxe do banco alvo. No T-SQL, LIMIT nao existe e vira TOP.
    """
    arvore = cast(exp.Query, sqlglot.parse_one(sql, read=dialeto))
    limite = arvore.args.get("limit")
    if isinstance(limite, exp.Limit):
        valor = limite.expression
        if isinstance(valor, exp.Literal) and valor.is_int and int(valor.name) <= teto:
            return sql
    elif isinstance(limite, exp.Fetch):
        contagem = limite.args.get("count")
        if isinstance(contagem, exp.Literal) and contagem.is_int and int(contagem.name) <= teto:
            return sql
    return arvore.limit(teto).sql(dialect=dialeto)
```

`tabelas_referenciadas` e `checar_allowlist` também têm `read="postgres"` hardcoded — trocar por parâmetro:

```python
def tabelas_referenciadas(sql: str, dialeto: str = "postgres") -> set[str]:
    ...
    arvore = cast(exp.Expression, sqlglot.parse_one(sql, read=dialeto))
    ...


def checar_allowlist(sql: str, allowlist: list[str], dialeto: str = "postgres") -> None:
    if "*" in allowlist:
        return
    permitidas = set(allowlist)
    for tab in tabelas_referenciadas(sql, dialeto):
        ...
```

O default `"postgres"` mantém os testes existentes de `test_policy.py` funcionando sem edição — eles testam a lógica de allowlist, que é dialeto-neutra.

- [ ] **Step 4: Rodar e ver passar**

```bash
uv run pytest tests/test_policy.py -q
```
Expected: todos passam (os 3 novos + os existentes intactos).

- [ ] **Step 5: Ajustar as chamadas em `server.py`**

```python
            if aplicar_allowlist:
                checar_allowlist(sql, self.s.allowlist, self.dialeto.sqlglot_dialeto)
            sql_limitado = injetar_limit(sql, self.s.max_rows + 1, self.dialeto.sqlglot_dialeto)
```

- [ ] **Step 6: Rodar tudo**

```bash
uv run pytest -q && uv run mypy src
```
Expected: **+3 testes**, zero vermelho, tipos limpos.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "fix(policy): injetar_limit emite no dialeto alvo

Com dialect=postgres hardcoded, SELECT TOP 9999 acima do teto virava
LIMIT 100 — sintaxe invalida no SQL Server. Defeito 5.1 do spec."
```

---

## Task 8: FIX 5.2 — `amostra` usa `sql_amostra` do dialeto

**Files:**
- Modify: `src/db_mcp/server.py`
- Test: `tests/test_server.py`

O `amostra` monta `SELECT * FROM {tabela} LIMIT {n}` na mão. O `injetar_limit` **devolve a string intocada** quando `n ≤ teto` (decisão deliberada de não mexer em SQL que já respeita o limite) — então o `LIMIT` cru chegaria no SQL Server e explodiria. Não dá pra confiar na transpilação.

- [ ] **Step 1: Escrever o teste**

Em `tests/test_server.py`:

```python
def test_amostra_usa_o_sql_do_dialeto(monkeypatch):
    # Defeito 5.2: amostra montava "LIMIT n" na mao, e o injetar_limit devolve a
    # string INTOCADA quando n <= teto. No SQL Server isso seria sintaxe invalida.
    from db_mcp.dialetos import obter_dialeto

    d = obter_dialeto("postgres")
    assert d.sql_amostra("clientes", 3) == 'SELECT * FROM "clientes" LIMIT 3'
```

- [ ] **Step 2: Rodar e ver o estado atual**

```bash
uv run pytest tests/test_server.py -k amostra -v
```

- [ ] **Step 3: Implementar em `src/db_mcp/server.py`**

```python
    @mcp.tool
    def amostra(tabela: str, n: int = 10) -> dict[str, Any]:
        """Primeiras N linhas de uma tabela liberada (n limitado ao teto; passa pela allowlist)."""
        try:
            n = min(max(n, 0), s.max_rows)  # clampa: n negativo viraria LIMIT -5 (erro cru)
            return nucleo.consultar(
                nucleo.dialeto.sql_amostra(tabela, n), cliente=_identificar_cliente()
            )
        except McpDbError as e:
            return {"erro": e.codigo, "detalhe": str(e)}
```

O `_validar_qualificado(tabela)` sai: o `sql_amostra` do dialeto agora faz o parse do nome com o sqlglot e o cita (`identify=True`). Um nome inválido levanta `ParseError` do sqlglot — que precisa virar `SqlInvalido`. Ajustar `sql_amostra` em `dialetos/postgres.py`:

```python
    def sql_amostra(self, tabela: str, n: int) -> str:
        from sqlglot.errors import ParseError

        from ..errors import SqlInvalido

        try:
            tab = sqlglot.parse_one(tabela, into=exp.Table, read=self.sqlglot_dialeto)
        except ParseError as e:
            raise SqlInvalido(f"nome de tabela inválido: {tabela!r}") from e
        return f"SELECT * FROM {tab.sql(dialect=self.sqlglot_dialeto, identify=True)} LIMIT {n}"
```

- [ ] **Step 4: Rodar**

```bash
uv run pytest -q
```
Expected: **+1 teste**, zero vermelho. Se algum teste de `amostra` quebrar por causa das aspas (`"clientes"` em vez de `clientes`), **o teste é que estava assumindo a interpolação crua** — atualizar a expectativa, não desfazer o quoting.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "fix(server): amostra usa sql_amostra do dialeto

Defeito 5.2: LIMIT montado na mao escapava da transpilacao porque o
injetar_limit devolve a string intocada quando n <= teto."
```

---

## Task 9: FIX 5.3 — introspecção por query parameters

**Files:**
- Modify: `src/db_mcp/server.py`
- Test: `tests/test_server.py`

Correção ao spec: são dois problemas em posições diferentes (ver a seção "Correção ao spec" no topo). A `amostra` (identificador) foi na Task 8. Aqui é a introspecção (literal de string), e a correção é **parâmetro**, não regex.

- [ ] **Step 1: Escrever o teste**

```python
def test_introspeccao_nao_e_injetavel_por_nome_de_schema(monkeypatch):
    # Antes: o nome ia interpolado dentro de um literal ('{schema}') e so a regex
    # segurava. Agora vai como parametro do driver — a aspa perde o poder de fechar
    # o literal, sem depender de filtro.
    capturado = {}

    class FakeDb:
        dialeto = obter_dialeto("postgres")

        def executar(self, sql, max_rows, params=None):
            capturado["sql"] = sql
            capturado["params"] = params
            return [], False

    s = Settings(pg_host="h", pg_dbname="d", pg_password="p")
    n = Nucleo(s, db=FakeDb())
    n.consultar(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
        params=("public'; DROP TABLE x --",),
        aplicar_allowlist=False,
    )
    assert capturado["params"] == ("public'; DROP TABLE x --",)
    assert "DROP" not in capturado["sql"]
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
uv run pytest tests/test_server.py -k injetavel -v
```
Expected: FAIL — `Nucleo.consultar() got an unexpected keyword argument 'params'`.

- [ ] **Step 3: `Nucleo.consultar` passa a aceitar `params`**

```python
    def consultar(
        self,
        sql: str,
        cliente: str = "stdio",
        aplicar_allowlist: bool = True,
        params: Any = None,
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        try:
            if not self.rl.permitir(cliente):
                raise LimiteDeTaxa("muitas consultas — tente novamente em instantes")
            validar(sql, self.dialeto, Perfil.SOMENTE_LEITURA)  # cadeado nº 3 (a)
            if aplicar_allowlist:
                checar_allowlist(sql, self.s.allowlist, self.dialeto.sqlglot_dialeto)
            sql_limitado = injetar_limit(sql, self.s.max_rows + 1, self.dialeto.sqlglot_dialeto)
            linhas, truncado = self.db.executar(sql_limitado, self.s.max_rows, params)
            ...
```

- [ ] **Step 4: Reescrever as quatro ferramentas de introspecção**

```python
    @mcp.tool
    def listar_tabelas(schema: str = "public") -> list[dict[str, Any]]:
        """Lista as tabelas de um schema."""
        return cast(
            "list[dict[str, Any]]",
            nucleo.consultar(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s AND table_type = 'BASE TABLE' "
                "ORDER BY table_name",
                cliente=_identificar_cliente(),
                aplicar_allowlist=False,
                params=(schema,),
            )["linhas"],
        )

    @mcp.tool
    def listar_views(schema: str = "public") -> list[dict[str, Any]]:
        """Lista as views de um schema."""
        return cast(
            "list[dict[str, Any]]",
            nucleo.consultar(
                "SELECT table_name FROM information_schema.views "
                "WHERE table_schema = %s ORDER BY table_name",
                cliente=_identificar_cliente(),
                aplicar_allowlist=False,
                params=(schema,),
            )["linhas"],
        )

    @mcp.tool
    def descrever_tabela(tabela: str, schema: str = "public") -> list[dict[str, Any]]:
        """Colunas e tipos de uma tabela."""
        return cast(
            "list[dict[str, Any]]",
            nucleo.consultar(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s "
                "ORDER BY ordinal_position",
                cliente=_identificar_cliente(),
                aplicar_allowlist=False,
                params=(schema, tabela),
            )["linhas"],
        )
```

`listar_schemas` não recebe entrada do usuário — fica como está.

**Atenção — o `%` vira problema:** o `sqlglot` precisa parsear esse SQL no validador, e `%s` não é sintaxe SQL válida em todo dialeto. Se `validar()` levantar `SqlInvalido` para as queries com `%s`, a saída é o `Nucleo` pular a validação quando `aplicar_allowlist=False` **e** `params is not None` — o SQL aí é constante do nosso código, não entrada do agente. Documentar essa exceção em comentário no código:

```python
            # SQL de introspeccao e constante do nosso codigo (nunca vem do agente) e
            # usa %s, que nao e SQL parseavel. Nesse caminho a validacao nao se aplica:
            # o que o agente controla vai por `params`, nunca por concatenacao.
            if params is None:
                validar(sql, self.dialeto, Perfil.SOMENTE_LEITURA)
                if aplicar_allowlist:
                    checar_allowlist(sql, self.s.allowlist, self.dialeto.sqlglot_dialeto)
                sql = injetar_limit(sql, self.s.max_rows + 1, self.dialeto.sqlglot_dialeto)
```

- [ ] **Step 5: Remover `_validar_ident`, `_validar_qualificado` e `_IDENT`**

Ficaram sem uso. Remover de `server.py` (linhas 20, 36-49 do original) e o `import re`.

- [ ] **Step 6: Rodar tudo, incluindo integração**

```bash
uv run pytest -q
docker compose up -d
PG_HOST=localhost PG_PORT=5433 PG_DBNAME=demo PG_USER=mcp_ro PG_PASSWORD=mcp_ro_demo \
  uv run pytest -q
```
Expected: **+1 teste novo, e os testes de `_validar_ident`/`_validar_qualificado` removidos** — esta é a única task do plano em que o total **cai**. Eles testavam uma função que deixou de existir; substituir pelo teste de parâmetro do Step 1 e **não** ressuscitar a regex.

Antes de remover, conferir o que exatamente sai:

```bash
grep -n "_validar_ident\|_validar_qualificado\|identificador inválido\|nome de tabela inválido" tests/test_server.py
```

Cada teste dessa lista precisa de um veredito consciente: **ou** ele testava a regex (some) **ou** ele testava que um nome malicioso não vaza pro SQL (fica, reescrito contra a proteção nova). Não apagar em bloco.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "fix(server): introspeccao por query parameters

Defeito 5.3 (parte literal): o nome ia interpolado num literal de string e
so a regex _IDENT segurava — restritiva demais (rejeitava 2fa_tokens, valido
no MySQL) e conceitualmente errada. Parametro mata a classe de injecao.
Os 3 drivers do projeto usam paramstyle pyformat (%s)."
```

---

## Task 10: `doctor` delega o probe de escrita

**Files:**
- Modify: `src/db_mcp/doctor.py`
- Test: `tests/test_doctor.py`

- [ ] **Step 1: Trocar `checar_somente_leitura` em `src/db_mcp/doctor.py`**

```python
def checar_somente_leitura(ctx: Contexto) -> Resultado:
    "Confirma que a conexão é somente-leitura"
    if ctx.conn is None or ctx.settings is None:
        raise PularChecagem("sem conexão")
    dialeto = obter_dialeto(ctx.settings.dialeto)

    class _Aceito(Exception):
        pass

    try:
        with ctx.conn.transaction():  # BEGIN ... sempre revertido
            ctx.conn.execute(dialeto.sql_probe_escrita())
            raise _Aceito()  # chegou aqui = write ACEITO (ruim)
    except dialeto.erros_readonly as e:
        return Resultado(
            True,
            "Somente-leitura confirmado",
            f"write recusado: {getattr(e, 'sqlstate', '')} {type(e).__name__}".strip(),
        )
    except _Aceito:
        return Resultado(
            False,
            "NÃO é somente-leitura",
            "o role conseguiu executar CREATE TABLE",
            "o usuário do MCP não pode ter DDL/DML: revogue tudo e conceda apenas SELECT",
        )
```

Import no topo: `from .dialetos import obter_dialeto`.

Nota pra Fase 2: `ctx.conn.transaction()` é API do psycopg. Quando o SQL Server entrar, a conexão do doctor também tem que vir do dialeto. Nesta fase fica — não inventar abstração pra um caso que ainda não existe (YAGNI).

- [ ] **Step 2: Rodar**

```bash
uv run pytest tests/test_doctor.py -q
```
Expected: passa.

- [ ] **Step 3: O `doctor` de verdade, contra o banco vivo — a prova da fase**

```bash
docker compose up -d
uv run db-mcp --env .env.demo doctor
```
Expected: exatamente 6 linhas verdes e `6 ok · 0 falha(s) · 0 pulada(s)`, incluindo `Somente-leitura confirmado — write recusado: 25006 ReadOnlySqlTransaction`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(doctor): probe de escrita delega ao dialeto"
```

---

## Task 11: Teste de fiação (e2e)

**Files:**
- Create: `tests/test_ataques_e2e.py`

Os testes de `test_sql.py` exercitam o validador **isolado, sem banco**. Um validador correto que não foi plugado não protege ninguém. Este arquivo prova que os guardrails estão **ligados** no caminho `Nucleo.consultar` → guardrails → pool → banco. Subconjunto representativo de propósito: a cobertura da lista de ataques é dos unitários; aqui o alvo é a fiação.

- [ ] **Step 1: Criar `tests/test_ataques_e2e.py`**

```python
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
    ('SELECT "pg_read_file"(\'/etc/passwd\')', SomenteLeitura),
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
```

- [ ] **Step 2: Rodar contra o banco vivo**

```bash
docker compose up -d
PG_HOST=localhost PG_PORT=5433 PG_DBNAME=demo PG_USER=mcp_ro PG_PASSWORD=mcp_ro_demo \
  uv run pytest tests/test_ataques_e2e.py -v
```
Expected: **15 passed** — 12 ataques parametrizados + 3 (o SELECT legítimo, a allowlist e a auditoria).

Nota sobre a fixture: ela é de escopo **função** de propósito, mesmo criando um pool por teste. `test_allowlist_esta_ligada_no_caminho_real` **muta** `nucleo.s.allowlist`; com escopo de módulo essa mutação vazaria pros testes seguintes e criaria falha fantasma. Contra o localhost o custo é irrelevante — corretude antes de velocidade.

- [ ] **Step 3: Confirmar que se pulam sem banco**

```bash
uv run pytest tests/test_ataques_e2e.py -q
```
Expected: `15 skipped`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test: fiacao e2e dos guardrails ate o banco

Os unitarios provam que o validador esta correto; estes provam que ele
esta plugado. Parametrizado por dialeto — fases 1 e 2 so acrescentam."
```

---

## Task 12: Docs, CI e verificação final

**Files:**
- Modify: `README.md`, `docs/DESIGN.md`, `docs/VISAO-GERAL.md`, `docs/03-arquitetura.md`, `CHANGELOG.md`, `.github/workflows/ci.yml`

- [ ] **Step 1: Atualizar os não-objetivos do `docs/DESIGN.md`**

O `DESIGN.md` §1 hoje diz:

```
- Escrita no banco (INSERT/UPDATE/DELETE/DDL): nunca.
- Outros SGBDs além de PostgreSQL.
```

Trocar por:

```markdown
- Escrita no banco (INSERT/UPDATE/DELETE/DDL): fora do escopo atual. Terá spec
  próprio. O princípio que já vale: a config da aplicação só pode **subtrair** do
  que o usuário do banco pode fazer, nunca somar — escrita real exigirá um usuário
  de banco com GRANT de escrita, que é passo de deployment, não linha de YAML.
- SGBDs além de PostgreSQL, MySQL e SQL Server. (MySQL e SQL Server chegam nas
  fases 1 e 2; ver `docs/superpowers/specs/2026-07-16-db-mcp-multi-dialeto-design.md`.)
- Paridade cega entre dialetos: onde o banco é mais fraco, o produto diz que é.
```

- [ ] **Step 2: Atualizar o `CHANGELOG.md`**

```markdown
## [0.3.0] — 2026-07-16

### Changed
- **BREAKING**: `pg-readonly-mcp` passa a se chamar `db-mcp` (pacote `db_mcp`,
  comando `db-mcp`). Quem tinha o MCP registrado no cliente precisa reapontar.
- Arquitetura multi-dialeto: o contrato `Dialeto` isola o que muda entre bancos.
  Nesta versão só o dialeto `postgres` existe; MySQL e SQL Server vêm em seguida.

### Fixed
- `injetar_limit` emitia sempre em sintaxe PostgreSQL. Sem efeito no dialeto
  `postgres`; teria quebrado o SQL Server.
- `amostra` montava `LIMIT` na mão e escapava da transpilação.
- Introspecção passa a usar query parameters em vez de interpolar o nome num
  literal de string protegido só por regex.
```

- [ ] **Step 3: O README ainda promete só Postgres**

O README abre com "Servidor MCP somente-leitura para PostgreSQL". Nesta fase **só o Postgres funciona de verdade**, então o README não pode prometer os três ainda. Ajuste mínimo e honesto: trocar o nome do comando, e acrescentar uma linha após o parágrafo de abertura:

```markdown
> **Estado atual:** o dialeto PostgreSQL está pronto. MySQL e SQL Server estão em
> desenvolvimento (fases 1 e 2 do design multi-dialeto). O código já está estruturado
> pra recebê-los, mas ainda não os suporta.
```

Não escrever a tabela dos três cadeados por dialeto agora: ela descreve bancos que ainda não funcionam. Ela entra na Fase 2, quando for verdade. **Documentar capacidade que não existe é o oposto da honestidade que o spec exige.**

- [ ] **Step 4: CI — nada muda de estrutura**

O job `integration` já sobe Postgres e semeia com `demo/init/*.sql`. Só conferir que os nomes de comando trocaram (não há `pg-readonly-mcp` no ci.yml após a Task 2, step 7).

```bash
grep -rn "pg-readonly\|pg_readonly" .github/ || echo "OK: CI limpo"
```

- [ ] **Step 5: A verificação final da fase — tudo junto**

```bash
docker compose down -v
docker compose up -d
uv sync
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
PG_HOST=localhost PG_PORT=5433 PG_DBNAME=demo PG_USER=mcp_ro PG_PASSWORD=mcp_ro_demo \
  uv run pytest -q
uv run db-mcp --env .env.demo doctor
```

Expected:
- ruff format: `All checks passed!`
- ruff check: `All checks passed!`
- mypy: `Success: no issues found`
- pytest sem banco: passa, com os de integração pulados
- pytest com banco: **tudo passa, zero skipped**
- doctor: `6 ok · 0 falha(s) · 0 pulada(s)`

**Se o doctor não fechar 6/6, a fase não terminou.** Era o critério desde o começo.

- [ ] **Step 6: Commit final**

```bash
git add -A
git commit -m "docs: atualiza nao-objetivos, changelog e estado do README para 0.3.0"
```

- [ ] **Step 7: Decisão de push (do Bruno, não do agente)**

O repo é **público**. Nada foi pushado até aqui. Antes do primeiro push, decidir:
1. `docs/superpowers/` vai pro repo público ou entra no `.gitignore`? O `.gitignore` já tem convenção de manter doc interno fora (`docs/plans/`, `docs/HANDOFF.md`) e `docs/superpowers/` **não** está coberto. Se for interno: `echo "docs/superpowers/" >> .gitignore && git rm -r --cached docs/superpowers`.
2. O commit de rename é `BREAKING CHANGE`. Confirmar que ninguém depende do nome antigo.

---

## Definição de pronto da Fase 0

- [ ] `uv run db-mcp --dialect postgres doctor` fecha **6/6** contra o container de demo.
- [ ] Suite completa verde com banco (**zero skipped**) e sem banco (integração pulada).
- [ ] `ruff check`, `ruff format --check` e `mypy src` limpos.
- [ ] Nenhuma ocorrência de `pg_readonly_mcp` / `pg-readonly-mcp` fora do `uv.lock` e do `.git`.
- [ ] Os três defeitos do spec (5.1, 5.2, 5.3) têm teste que **falha** se alguém reverter a correção.
- [ ] `dialetos/base.py` não importa driver nenhum.
- [ ] Zero funcionalidade nova. Se apareceu, saiu do escopo.
