---
tipo: projeto
cliente: interno
produto: —
no_ar: não
atividade: ativo
stack: ["Python 3.11+", "uv", "FastMCP", "psycopg3", "mysql-connector", "sqlglot"]
ultima_atividade: 2026-07-21
proxima_acao: "Fase 1 (MySQL) mergeada no main público e tagueada v0.4.0 (CI 7/7 verde). Próximo: planejar a Fase 2 (SQL Server) — herda tsql≠sqlserver, OPENQUERY/OPENROWSET, WAITFOR DELAY e a ausência de reset de sessão"
repo: git+remote
tags: [mcp, banco-de-dados, open-source, postgres, mysql]
---
# db-mcp

## Estado atual
**Fase 1 (MySQL) CONCLUÍDA e verificada em 2026-07-21.** O produto fala com **dois bancos**:
`db-mcp --dialect {postgres,mysql} doctor` fecha **6/6** nos dois. Versão **0.4.0**.

**Tudo vive no `main`.** A Fase 1 foi mergeada (`--no-ff`, `2817312`) e tagueada **`v0.4.0`**
em 2026-07-21; o CI do `main` fechou **7/7** (lint+types, testes em ubuntu/windows × py3.12/3.13,
integração Postgres e MySQL com `doctor` 6/6 contra banco real). As branches de fase foram
apagadas — `refactor/fase-1-mysql` já não existe. Repo público **em dia** com o que foi entregue.

Medido localmente com os containers de demo (e reproduzido no CI):

| | sem banco | Postgres | MySQL |
|---|---|---|---|
| suíte (229 testes) | 191 ✅ / 38 ⏭️ | 215 ✅ / 14 ⏭️ | 216 ✅ / 13 ⏭️ |
| `doctor` | — | **6/6** | **6/6** |
| recusa de escrita | — | `25006 ReadOnlySqlTransaction` | `42000` / `1142` |

`ruff` · `ruff format` · `mypy src` limpos. **`base.py`, `db.py`, `server.py` e `doctor.py` não
importam `psycopg` nem `mysql`** — o núcleo é dialeto-agnóstico de fato, não de intenção.
Os 13/14 skips são **auditados** (`-rs`): é o corpus de ataque do *outro* dialeto se pulando,
e deve mesmo. A união dos dois modos cobre os 229.

**A aposta da Fase 0 se pagou:** o dialeto novo custou **um arquivo** (`dialetos/mysql.py`) e
**uma linha** no `_REGISTRO`. Nenhum arquivo do núcleo foi tocado para o MySQL existir.

## O que é
Servidor MCP somente-leitura para bancos SQL. Dá a agentes de IA (Claude Desktop, Claude Code,
automações) acesso de introspecção e `SELECT`, sem escrever, alterar schema ou derrubar o banco.

Um repo, um pacote, dialetos como módulos: **`postgres` e `mysql` prontos**, `sqlserver` na Fase 2.
O código não conhece nenhum banco específico — você aponta pelo config. Nenhum host, senha ou nome
de tabela real fica no repositório.

## Stack & como rodar
Python 3.11+ com [`uv`](https://docs.astral.sh/uv/). Não está no PyPI — instala-se clonando.

```bash
uv sync --extra mysql                          # o driver do MySQL é extra OPCIONAL
docker compose up -d                           # Postgres de demo na 5433
docker compose --profile mysql up -d           # MySQL de demo na 3307
uv run db-mcp --env .env.demo doctor           # 6/6
uv run db-mcp --env .env.demo-mysql doctor     # 6/6
docker compose --profile mysql down -v         # derruba e apaga tudo
```

**Testes** — a suíte é a mesma; o banco apontado decide o que roda:
```bash
uv run pytest -q                                    # 191/38 (integração se auto-pula)
DB_HOST=localhost DB_PORT=5433 DB_DBNAME=demo DB_USER=mcp_ro DB_PASSWORD=mcp_ro_demo \
  uv run pytest -q                                  # 215/14
DIALETO=mysql DB_HOST=127.0.0.1 DB_PORT=3307 DB_DBNAME=demo DB_USER=mcp_ro \
  DB_PASSWORD=mcp_ro_demo uv run pytest -q          # 216/13
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

⚠️ **Rode as DUAS suítes.** Vários bugs desta fase passavam sem banco e só apareceram contra o
banco vivo. O gate da integração é `.env` existir **ou** `DB_HOST` no ambiente.

## Estrutura
```
src/db_mcp/
├── server.py          casca MCP (FastMCP) + Nucleo (toda lógica auditável)
├── db.py              fachada fina; delega ao dialeto
├── config.py          pydantic-settings (.env + config.yaml)
├── doctor.py          as 6 checagens — não importa driver nenhum
├── cli.py             `db-mcp` + `--dialect` (chega no doctor desde a Fase 1)
├── guardrails/        sql.py (validador) · policy.py (allowlist + LIMIT) · ratelimit.py
└── dialetos/          base.py (Protocol) · postgres.py · mysql.py   ← sqlserver entra aqui
```

**Ordem de leitura pra retomar:** [spec do design](docs/superpowers/specs/2026-07-16-db-mcp-multi-dialeto-design.md)
→ [plano da Fase 1](docs/superpowers/plans/2026-07-20-db-mcp-fase-1-mysql.md) (feito, com os
resultados medidos no fim). Manual do produto em `docs/`.

## Ambiente & acessos
- **Nenhum deployment real.** Só os dois containers de demonstração.
- **Credenciais dos demos são FAKE e públicas** — `mcp_ro`/`mcp_ro_demo` em `localhost:5433`
  (Postgres) e `127.0.0.1:3307` (MySQL). Estão em `.env.demo`, `.env.demo-mysql` e nos
  `demo/init*/03-mcp-ro.sql`. Não são segredo, são parte do exemplo.
- **Segredos reais** vão em `.env` / `config.yaml`, ambos git-ignored; cada ambiente em
  `deployments/<ambiente>.md` (git-ignored). Ponteiro pro cofre `CHAVES/` — nunca inline aqui.
- ⚠️ **A ferramenta Read do Claude é bloqueada em arquivos `.env*`** — para descobrir os
  parâmetros dos demos, ler `docker-compose.yml` e os `demo/init*/03-mcp-ro.sql`.

## Decisões & gotchas

### Decisões travadas (2026-07-16) — detalhe no [spec §1](docs/superpowers/specs/2026-07-16-db-mcp-multi-dialeto-design.md)
**Um repo**, dialetos como módulos (3 repos fariam a lista de funções perigosas **divergir**) ·
**pool nativo por dialeto** · **pymssql** (o pyodbc exige `msodbcsql18` no SO) ·
**mysql-connector** (tem pool **e** `RESET CONNECTION`) · **só leitura** — escrita ganha spec próprio.

### O princípio da escrita futura
**O cadeado nº 1 (o usuário do banco) é a autoridade. A config da aplicação só pode SUBTRAIR do
que ele já pode fazer, nunca somar.** `MODE=write` num `mcp_ro` continua não escrevendo. Escrita
real exigirá usuário de banco diferente com GRANT — passo de deployment, não linha de YAML.

### 🚨 Os cadeados NÃO portam igual entre bancos (Postgres e MySQL, MEDIDO)
| | PostgreSQL | MySQL | SQL Server (Fase 2) |
|---|---|---|---|
| Cadeado nº 1 | `default_transaction_read_only` **no role** + GRANT | **só GRANT** + `SET SESSION TRANSACTION READ ONLY` por conexão | **só GRANT/DENY** |
| Quem garante o read-only | o **servidor** | a **aplicação** (reaplica a cada checkout) | — |
| Reset de sessão | `DISCARD ALL` | `RESET CONNECTION` | **não existe** |
| Força real | cinto **e** suspensório | suspensório forte + cinto do app | **só suspensório** |

Está documentado no README, `docs/02-preparar-o-banco.md` e `00-para-leigos.md`, **com a
consequência prática escrita como instrução**: no MySQL o `GRANT SELECT` restrito é a proteção
principal, e **nunca conceder `FILE`** (habilita `INTO OUTFILE`/`load_file`).

### 🔴 O único cadeado que falha ABERTA (medido, mysql-connector 9.7 / MySQL 8.4)
`pool_reset_session=True` **ZERA** o `SET SESSION TRANSACTION READ ONLY` no retorno ao pool
(mesmo `CONNECTION_ID`, `1 → 0`) e o `max_execution_time` junto. Aplicá-los uma vez na criação do
pool deixaria as conexões **graváveis e sem timeout do 2º checkout em diante, em silêncio**.
Por isso `_PoolMySQL.connection()` reaplica **a cada checkout** — e
`test_mysql_reaplica_read_only_a_cada_checkout` existe para impedir que alguém "simplifique" isso.

### 🔒 O invariante do um-banco-só (2026-07-21)
**Qualquer referência que nomeie um catalog (`banco.schema.tabela` ou
`servidor.banco.schema.tabela`) é RECUSADA**, inclusive com `allowlist=["*"]` — o `*`
desliga a allowlist, não o invariante. A regra não olha a config, o que a torna auditável
sem saber em que banco estamos, e a checagem anda por `find_all` e **não** pela análise de
escopo (um cadeado não pode depender do `traverse_scope`, que tem fallback por poder falhar).

**Por que existiu o buraco:** `tabelas_referenciadas` montava o nome com `t.db + t.name` e
**descartava o `t.catalog`** — `outrodb.public.clientes` virava `public.clientes` e casava
com a entrada feita pro banco corrente. No Postgres e no MySQL é inofensivo (medido: dão
`cross-database references are not implemented` e `1064`); **o SQL Server executa nome de 3
partes**. Consequência assumida: `demo.public.clientes` (o próprio banco, SQL válido no PG)
também passa a ser recusado.

📏 **Demonstrado contra um SQL Server 2022 real (2026-07-21), com a precisão que o commit
`26f2bff` não teve.** Aquele commit disse "um login costuma enxergar vários bancos da mesma
instância", o que é **largo demais**. O que de fato acontece:
- Por **padrão** um login **não** lê dado de usuário de outro banco: erro **916**
  (`server principal is not able to access the database`). O cadeado nº 1 segura.
- O vazamento real exige o login estar **legitimamente mapeado em mais de um banco** — arranjo
  comum (cópias dev/homolog/prod, multi-tenant). Aí o cadeado nº 1 **para de segurar**, e a
  allowlist era a única coisa de pé. Medido: com GRANT nos dois bancos e allowlist
  `['dbo.clientes']`, o servidor entregou `financeiro.dbo.clientes` e **a allowlist antiga
  deixava passar** quando o `schema.tabela` coincidia (comuníssimo) — ou **sempre**, se a
  entrada fosse não-qualificada (`['clientes']`), que casa pelo último segmento.

⚠️ Este foi o **primeiro caso em que um dialeto novo exigiu mexer no núcleo** — o padrão
"um arquivo + uma linha" vale pro dialeto, não pros cadeados compartilhados.

### 🚨 SQL Server vaza METADADO por padrão (medido 2026-07-21) — entrada da Fase 2
Um login com `GRANT SELECT` em **uma** tabela ainda enxerga, sem nenhum grant extra:
lista de **todos os bancos** da instância (`sys.databases`, 6 linhas), **todos os logins SQL**
(`sys.sql_logins`), e o **catálogo do `master`** (`master.sys.objects`). Não é dado de usuário,
mas é reconhecimento de terreno de graça — e **não tem equivalente no Postgres/MySQL**.

Medido que **fecha** (vai virar receita no `docs/02-preparar-o-banco.md` da Fase 2):
`DENY VIEW ANY DATABASE` · `DENY VIEW ANY DEFINITION` · `REVOKE CONNECT FROM guest` nos demais
bancos. Depois disso: `master.sys.objects` cai de 3 pra **0 linhas**, e `sys.databases` de 6
pra **3** (`master`/`tempdb`/o próprio — o piso do SQL Server, não dá pra zerar).

### Gotchas vivos
- **Repo PÚBLICO** — o único do portfólio. Pense antes de commitar.
- 🪤 **`"sqlserver"` NÃO é nome de dialeto do sqlglot — lá se escreve `tsql`** (medido), e
  `"sqlserver"` é exatamente a string já no `Literal` do `config.py`. Quem copiar o padrão do
  `postgres.py`/`mysql.py` (onde `nome == sqlglot_dialeto` por coincidência) leva `ValueError` em
  toda query, **sem auditoria**. ✅ Guardado no CI pelo `test_invariante_todo_dialeto`.
- ⚠️ **`funcs_proibidas` vazia falharia ABERTA** — um dialeto stub liberaria `load_file`.
  ✅ Guardado pelo mesmo teste de invariante. Contrapeso: as `TAGS_PROIBIDAS` seguem barrando
  escrita mesmo com a lista vazia.
- 🪤 **`TokenError` NÃO é subclasse de `ParseError`** — são irmãs sob `SqlglotError` (medido).
  **Qualquer `except ParseError` novo reabre** a recusa-sem-auditoria corrigida no `74aba49`.
- **`INTO OUTFILE`/`DUMPFILE` só são barrados por `ParseError`** — falham fechado **por acidente**.
  ✅ Regressão em `test_sql_mysql.py` que exige **recusa** (`McpDbError`), não o mecanismo: se o
  sqlglot passar a parseá-los, o teste avisa em vez de o buraco abrir calado.
- 🪤 **No MySQL, aspas duplas são STRING literal — a citação é a CRASE** (medido). Copiar do
  corpus do Postgres o caso `"load_file"(...)` testa uma coisa que não existe: ele morre no parser
  (`sql_invalido`), enquanto `` `load_file`(...) `` é que chega na blocklist (`somente_leitura`).
- 🔴 **mysql-connector: fechar cursor com linhas por ler estoura `Unread result found`**, e o
  `close()` seguinte falha mascarando o erro **e vazando a conexão do pool**. O caminho normal de
  truncagem (`fetchmany(n)` + `fetchone()`) dispara isso. Fix: `conn.consume_results()` antes do
  `cur.close()` (o psycopg descarta sozinho). **Toda query truncada quebrava antes disso.**
- **O CI DEVE usar `--all-extras`** — sem o driver, o mypy não resolve o import **e** o
  `test_invariante_todo_dialeto[mysql]` se pula, silenciando o gate onde ele mais importa.
- **A allowlist é defesa em profundidade, não o limite último.** O isolamento forte está no banco.
  Ver `docs/DESIGN.md §5`.

## Backlog
- [x] **Fase 0 — multi-dialeto (2026-07-16 a 07-20).** 12 tasks, `52bd464..30ebd29`. O núcleo
  deixou de conhecer Postgres; contrato `Dialeto` + `dialetos/postgres.py`; 3 defeitos do spec
  corrigidos com regressão; fiação e2e. Detalhe no
  [plano](docs/superpowers/plans/2026-07-16-db-mcp-fase-0-multi-dialeto.md).
- [x] **Fase 1 — MySQL (2026-07-20 e 07-21).** 10 tasks, `2e484a4..950843c`. Config `db_*` →
  introspecção no `Nucleo` → doctor dialeto-aware → `erro_readonly` predicado →
  **`dialetos/mysql.py`** → corpus de ataque → demo MySQL → CI com os dois bancos → docs honestos
  → verificação final. Resultados medidos no fim do
  [plano](docs/superpowers/plans/2026-07-20-db-mcp-fase-1-mysql.md).
- [x] **Merge da Fase 1 pro `main` (2026-07-21).** `--no-ff` em `2817312`, tag **`v0.4.0`**,
  CI do `main` **7/7**. Branches de fase apagadas (local e remoto). O repo público passou a
  mostrar o MySQL.
- [ ] 🎯 **Fase 2 — SQL Server.** Plano próprio. Herda os gotchas do `tsql`/`sqlserver`,
  `OPENQUERY`/`OPENROWSET`/`OPENDATASOURCE` (passam pelo validador com raiz `Select`),
  `WAITFOR DELAY` (só `ParseError`), nome de 3 partes cross-database, e a ausência de reset de
  sessão. A tabela dos cadeados já tem a coluna dele — preenchê-la quando existir.
- [ ] 🔴 **`STATEMENT_TIMEOUT_MS=0` desliga o timeout nos TRÊS dialetos, em silêncio.**
  Achado medindo durante a Fase 2 (2026-07-21); **é do núcleo, não do SQL Server**, e a
  decisão foi corrigir **depois** da Fase 2, em commit próprio, para não misturar escopo.
  Medido contra os bancos vivos: `SET statement_timeout = 0` (Postgres) e
  `SET max_execution_time = 0` (MySQL) são **aceitos e significam SEM limite**; no pymssql
  `timeout=0` idem. Os três dialetos repassam o valor sem clamp
  (`postgres.py:118`, `mysql.py:85`, `sqlserver.py:_conectar`), e `config.py:41` tem
  `statement_timeout_ms: int = 5000` **sem validação nenhuma**. Um operador que escreva `0`
  achando que é "o padrão" perde o guardrail contra query desgovernada.
  ⚠️ **Não usar `Field(ge=1000)`** — amarraria o núcleo à granularidade de segundo de *um*
  driver e proibiria 999 ms, que é legítimo no Postgres e no MySQL. O certo é barrar `0` e
  negativos (`gt=0`). O `max(1, ...)` do `sqlserver.py` continua necessário de qualquer forma
  (guardado por `test_sqlserver_timeout_para_o_driver_nunca_e_zero`).
- [ ] **Tags retroativas `v0.2.0` e `v0.3.0`.** O CHANGELOG declara as três versões; só a
  `v0.4.0` existe no git. Baixa prioridade — exige achar os commits certos de cada release.
- [ ] **Apagar `refactor/fase-0-multi-dialeto`** (local e remoto). Aponta pra `76b123d`, hoje
  ancestral do `main` — está totalmente incorporada e é peso morto.
- [ ] **Revisão retroativa da Task 2 da Fase 0** (o rename) — a formal nunca rodou.
- [ ] **Escrita configurável** — spec próprio. Ver o princípio acima.
- [ ] Todo commit tem autor `bruno.outcore@guarida.com.br`, ligando a identidade pública do GitHub
  ao empregador. Considerar `git config user.email` dedicado se a separação importar.

## Pendências — auditoria 2026-07-17
Todas as pendências desta auditoria foram fechadas até 2026-07-21 (docs de arquitetura e
não-objetivos corrigidos, `main` trazido em dia na época, `tests/test_ataques_e2e.py` criado,
recusas de introspecção e de amostra passando a auditar, CHANGELOG em dia).
✅ **Corrigido em 2026-07-21:** esta seção afirmava que a skill `setup-db-mcp` "ainda escreve
chaves `pg_*` e vai gerar config quebrada". **Era falso** — ela escreve o `.env` a partir do
`.env.example`, que já usa `DB_*`. Só a descrição dizia "PostgreSQL"; atualizada.
