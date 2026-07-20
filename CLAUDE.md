---
tipo: projeto
cliente: interno
produto: —
no_ar: não
atividade: ativo
stack: ["Python 3.11+", "uv", "FastMCP", "psycopg3", "sqlglot"]
ultima_atividade: 2026-07-20
proxima_acao: "Fase 0 fechada — decisão do Bruno: push dos 5 commits + merge de main; depois Fase 1 (MySQL)"
repo: git+remote
tags: [mcp, banco-de-dados, open-source, postgres]
---
# db-mcp

## Estado atual
**Fase 0 CONCLUÍDA (2026-07-20) — refatoração multi-dialeto pronta, ainda só com PostgreSQL.**
Branch `refactor/fase-0-multi-dialeto`: **19 commits à frente de `main`, 5 ainda NÃO-pushados**
(os 4 de T9-T12 desta sessão — `bc8f901..30ebd29` — mais o de auditoria de 2026-07-17). Working
tree limpo. As **12 tasks** do plano estão feitas.

- 📄 **[Spec do design multi-dialeto](docs/superpowers/specs/2026-07-16-db-mcp-multi-dialeto-design.md)**
  (aprovado) e **[plano da Fase 0 (12 tasks)](docs/superpowers/plans/2026-07-16-db-mcp-fase-0-multi-dialeto.md)**.
  Fases 1 (MySQL) e 2 (SQL Server) ganham planos próprios agora que a 0 fechou.
- ✅ **O núcleo é dialeto-agnóstico:** `db.py` **não importa `psycopg`** — pool, cursor-dict, tradução
  de erro do driver **e o probe de escrita do doctor** (T10) vêm do contrato `Dialeto`. Os **3 defeitos
  do spec** (5.1 policy, 5.2 amostra, 5.3 introspecção) estão corrigidos, cada um com teste de regressão.
- 🧪 **Testes:** 126 passed / 24 skipped sem banco · **150 passed / zero skipped** com o demo Docker ·
  `doctor` **6/6** contra o demo recriado do zero · ruff/format/mypy limpos. A Fase 0 não mudou
  comportamento no Postgres — a suíte existente foi a rede de segurança. A **fiação e2e** (T11,
  `tests/test_ataques_e2e.py`) prova que os guardrails estão *plugados*, não só corretos isolados.
- 🎯 **A T9 corrigiu o plano de novo (medido):** ele mandava DESLIGAR o validador quando
  `params is not None`, supondo que `%s` não fosse SQL parseável. Medido no sqlglot 30.12: `%s`
  parseia, passa `validar()` e `injetar_limit()` — o **cadeado nº 3 fica LIGADO em todo caminho**.
  A introspecção agora manda o nome por query parameter (`%s`), matando a classe de injeção; a regex
  `_IDENT`/`_validar_ident` saiu.
- ⚠️ **A Task 2 (rename) nunca passou pela revisão formal** — de pé por aprovação do Bruno +
  verificação manual. Revisão retroativa segue no Backlog.
- 📖 **Spec, plano, `CLAUDE.md` e `worklog.md` são públicos, por decisão (2026-07-16).** Nada aqui
  tem segredo — os segredos moram em `.env`/`config.yaml`/`deployments/`, todos git-ignored.

**Próxima ação:** **decisão do Bruno** — push dos **5 commits** pra `origin` (repo PÚBLICO,
outward-facing) e merge/fast-forward de `main` (19 commits atrás). Depois, **Fase 1 (MySQL)** com
plano próprio. 📌 **Uma lacuna do Backlog sobreviveu à Fase 0:** `amostra` com nome inválido recusa
**sem auditoria** (o `sql_amostra` levanta ANTES do `Nucleo.consultar`; a T9 fechou a irmã da
`descrever_tabela` ao remover o `_validar_ident`, mas a do `amostra` continua). Vale fechar antes
ou junto da Fase 1.

## O que é
Servidor MCP somente-leitura para bancos SQL. Dá a agentes de IA (Claude Desktop, Claude Code,
automações) acesso de introspecção e `SELECT`, sem escrever, alterar schema ou derrubar o banco.

Era `pg-readonly-mcp` (só PostgreSQL). Está virando **multi-dialeto**: um repo, um pacote, dialetos
como módulos (`postgres` hoje; `mysql` e `sqlserver` nas Fases 1 e 2). O nome perdeu o `readonly`
porque escrita configurável é ambição futura — e `readonly` no nome viraria mentira.

O código não conhece nenhum banco específico: você aponta o MCP pro seu banco preenchendo a config.
Nenhum host, senha ou nome de tabela real fica no repositório.

## Stack & como rodar
Python 3.11+ com [`uv`](https://docs.astral.sh/uv/). Não está no PyPI — instala-se clonando.

```bash
uv sync                                  # instala tudo
docker compose up -d                     # Postgres de demo semeado na porta 5433
uv run db-mcp --env .env.demo doctor     # deve fechar 6/6 verde
uv run db-mcp --env .env.demo            # sobe o servidor (stdio)
docker compose down -v                   # derruba e apaga
```

**Testes:**
```bash
uv run pytest -q                         # 126 passed, 24 skipped (integração se auto-pula sem banco)
# com banco (destrava os de integração → 150 passed, zero skipped):
PG_HOST=localhost PG_PORT=5433 PG_DBNAME=demo PG_USER=mcp_ro PG_PASSWORD=mcp_ro_demo uv run pytest -q
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

O gate dos testes de integração é `.env` existir **ou** `PG_HOST` no ambiente
(`tests/test_e2e_integration.py:10`) — sem isso eles se pulam sozinhos, e é normal.

## Estrutura
```
src/db_mcp/
├── server.py          casca MCP (FastMCP) — dialeto-agnóstica
├── db.py              fachada fina; delega ao dialeto
├── config.py          pydantic-settings (.env + config.yaml)
├── doctor.py          as 6 checagens de saúde
├── cli.py             `db-mcp` + `--dialect`
├── guardrails/        sql.py (validador) · policy.py (allowlist + LIMIT) · ratelimit.py
└── dialetos/          base.py (o Protocol + Perfil) · postgres.py  ← MySQL/SQL Server entram aqui
```

**Ordem de leitura pra retomar:** `docs/superpowers/specs/2026-07-16-…-design.md` (o porquê de tudo,
incl. a tabela honesta dos cadeados) → `docs/superpowers/plans/2026-07-16-…-fase-0-….md` (as 12 tasks).
Manual do produto em `docs/` (`DESIGN.md`, `01-instalacao.md`, `02-preparar-o-banco.md`,
`03-arquitetura.md`, `04-troubleshooting.md`, `00-para-leigos.md`).

## Ambiente & acessos
- **Nenhum deployment real ainda.** O único banco em uso é o container de demonstração.
- **Credenciais do demo são FAKE e públicas** (`mcp_ro` / `mcp_ro_demo` @ `localhost:5433/demo`,
  em `.env.demo` e `demo/init/03-mcp-ro.sql`) — não são segredo, são parte do exemplo.
- **Segredos reais** (quando houver deployment) vão em `.env` / `config.yaml`, ambos **git-ignored**,
  e cada ambiente é registrado em `deployments/<ambiente>.md` (git-ignored). Ponteiro para o cofre
  `CHAVES/` da raiz — **nunca inline aqui**.
- ⚠️ **A ferramenta Read do Claude é bloqueada por permissão em arquivos `.env*`** — para descobrir
  os parâmetros do demo, ler `docker-compose.yml` e `demo/init/03-mcp-ro.sql`.

## Decisões & gotchas

### Decisões travadas (2026-07-16) — detalhe no [spec §1](docs/superpowers/specs/2026-07-16-db-mcp-multi-dialeto-design.md)
**Um repo**, dialetos como módulos (3 repos fariam a lista de funções perigosas **divergir** —
corrige-se um bypass no Postgres e esquece nos outros) · **pool nativo por dialeto** (o `DBUtils` não
roda `DISCARD ALL`, que aqui é segurança; o SQLAlchemy é dependência grande demais num produto cuja
tese é superfície pequena) · **pymssql** (o pyodbc exige `msodbcsql18` no SO e quebra o "clona e
roda") · **mysql-connector** (tem pool **e** `RESET CONNECTION`; o PyMySQL não tem nenhum dos dois) ·
**só leitura neste spec** — escrita ganha spec próprio.

### O princípio da escrita futura
**O cadeado nº 1 (o usuário do banco) é a autoridade. A config da aplicação só pode SUBTRAIR do que
ele já pode fazer, nunca somar.** `MODE=write` num `mcp_ro` continua não escrevendo — o banco recusa.
Escrita real exigirá um **usuário de banco diferente com GRANT**, que é passo de deployment, não
linha de YAML. A costura já está no lugar (`validar(sql, dialeto, perfil)`, `Perfil` com um valor só).

### 🚨 Os cadeados NÃO portam igual entre bancos
| | PostgreSQL | MySQL | SQL Server |
|---|---|---|---|
| Cadeado nº 1 | `default_transaction_read_only` **no role** + GRANT | `SET SESSION TRANSACTION READ ONLY` + GRANT | **só GRANT/DENY** |
| Reset de sessão | `DISCARD ALL` | `RESET CONNECTION` | **não existe** |
| Força real | cinto **e** suspensório | cinto fraco + suspensório | **só suspensório** |

O README afirma *"o próprio Postgres recusa a escrita"* — **essa frase fica FALSA no SQL Server.**
Corrigir os docs é entregável da Fase 2, não nota de rodapé. **Não escrever essa tabela no README
antes de o dialeto existir** — documentar capacidade inexistente é o oposto da honestidade.

### Gotchas
- **Repo PÚBLICO** — o único do portfólio (os outros são privados). Pense antes de commitar.
- **O núcleo já era dialeto-agnóstico** (medido no sqlglot 30.12, não presumido): os nós
  (`Insert`/`Update`/`Delete`/`Create`/`Drop`) têm nome **idêntico** nos 3 dialetos, `exp.Anonymous`
  pega função perigosa nos 3, e `LIMIT` vira `TOP` sozinho no tsql. **Muda a LISTA, não o mecanismo.**
- **`--dialect` não alcança o subcomando `doctor`** (ele carrega o `Settings` sozinho). Inofensivo
  enquanto só `postgres` resolve; na Fase 1 a flag passa a **mentir em silêncio**. Marcador
  `# FASE 1:` no `cli.py`.
- **`INTO OUTFILE` (MySQL) e `WAITFOR DELAY` (T-SQL) só são barrados por `ParseError`** — falham
  fechado, mas **por acidente**. Um upgrade do sqlglot que passe a parseá-los abre o buraco em
  silêncio → teste de regressão nasce junto do dialeto (Fases 1 e 2).
- **`OPENQUERY`/`OPENROWSET`/`OPENDATASOURCE` passam pelo validador** com raiz `Select` — precisam
  entrar na lista do T-SQL (Fase 2).
- 🪤 **`"sqlserver"` NÃO é nome de dialeto do sqlglot — lá se escreve `tsql`** (medido: `postgres` e
  `mysql` o sqlglot aceita, `sqlserver` dá `ValueError: Unknown dialect`). E `"sqlserver"` é
  exatamente a string que já está no `Literal` do `config.py:33`. O nome do produto e o do sqlglot
  coincidem em 2 dos 3 dialetos e quebram **só** no terceiro, então quem copiar o padrão do
  `postgres.py` (onde `nome == sqlglot_dialeto`, por coincidência) na Fase 2 escreve
  `sqlglot_dialeto = "sqlserver"` e leva `ValueError` em toda query. O `Dialeto` tipa o campo como
  `str` puro → o mypy não pega. Pior: o `ValueError` escapa do `except SqlglotError` do `validar`
  (ele não é da família do sqlglot) **e** do `except McpDbError` do `server.py` → sai **sem
  auditoria**. Falha **fechada** (a query morre, nada vaza) e é inalcançável hoje — mas é o motivo
  nº 1 do teste de invariante no Backlog.
- 🪤 **`TokenError` NÃO é subclasse de `ParseError` — são irmãs sob `SqlglotError`** (medido). Quando
  o **tokenizer** morre antes do parser (aspa nunca fechada), o sqlglot levanta `TokenError`. Um
  `except ParseError` — que era o código até 2026-07-17 e o que o **plano ainda prescreve na T8** —
  a deixa vazar crua: não vira `SqlInvalido`, escapa do `except McpDbError` do `server.py`, e a
  recusa sai **sem rastro na auditoria**. Falhava fechado, mas sem trilha. Corrigido no `74aba49`
  (`except SqlglotError` no `sql.py` e no `sql_amostra`). **Qualquer `except ParseError` novo
  reabre isto** — a família inteira é `SqlglotError`.
- ⚠️ **`funcs_proibidas` vazia falharia ABERTA — é o único ponto da costura nova com essa assimetria.**
  Um dialeto stub na Fase 1 com a lista por preencher liberaria `SELECT load_file('/etc/passwd')`.
  Contrapeso verificado: com `funcs_proibidas` vazia o `DELETE FROM t` **continua barrado** pelo
  `TAGS_PROIBIDAS` — ou seja, manter as tags no módulo é carga estrutural, não estética: dialeto mal
  escrito não destranca escrita. É o motivo nº 2 do teste de invariante.
- **A allowlist é defesa em profundidade, não o limite último.** O isolamento forte tem que estar no
  banco (GRANT só nas tabelas certas). Ver `docs/DESIGN.md §5` — ele é honesto sobre o que a análise
  de SQL **não** cobre.

## Backlog
- [x] **Fase 0 · T1-T5 (2026-07-16):** pasta/remote → pacote `db_mcp` + comando `db-mcp` → config
  `dialeto` + `--dialect` → contrato `Dialeto` + `dialetos/postgres.py` → `db.py` delega.
  Commits `52bd464..8864f69`. **127 passed / zero skipped** contra o Postgres vivo.
- [x] **Fase 0 · T6 (2026-07-16):** `validar(sql, dialeto, perfil)`; `FUNCS_PROIBIDAS` saiu do módulo
  e vem do dialeto (`TAGS_PROIBIDAS` ficou — os nós são idênticos nos 3); `test_sql.py` parametrizado.
  Commit `7c39ada`. **45 testes em `test_sql.py` antes e depois** (nenhum ataque deixou de ser
  barrado) · 118/9 sem banco · revisões de spec e de qualidade passaram, zero Critical.
- [x] **Fase 0 · T7 (2026-07-17):** `policy.py` lê **e** emite no dialeto alvo. Commit `646ba6b`.
  **Desvio do plano, aprovado:** `tabelas_referenciadas`/`checar_allowlist` ficaram com o dialeto
  **obrigatório**, sem o default `"postgres"` que o plano previa — são caminho de segurança, e com
  default um caller esquecido passa calado. Dividendo imediato: o mypy acusou na hora os 2 callers
  do `server.py`. **Correção ao doc:** o defeito **não** era `TOP 9999` → `LIMIT 1000` (isso dava
  `ParseError`, falha fechada); era a query T-SQL **sem limite**, que parseia nos dois dialetos e
  saía com `LIMIT 100` grudado. O teste novo mira o caso real.
- [x] **Fase 0 · T8 (2026-07-17):** `amostra` usa `sql_amostra` do dialeto. Commit `67b6485`. O
  `_validar_qualificado` (regex no `server.py`) **saiu** — ficou sem caller, e o parse
  `into=exp.Table` do dialeto é mais estrito. Corpus de ataques re-apontado pro `sql_amostra`:
  **de 4 para 8 casos**, nenhum perdido. Fiação verificada no servidor real (o SQL auditado saiu
  `SELECT * FROM "clientes" LIMIT 2`, com aspas = assinatura do dialeto). **Mudança de
  comportamento registrada em teste:** nome de 3 partes agora passa o check (a regex barrava) e
  morre no banco — inócuo no Postgres, **decisão de segurança na Fase 2** (o SQL Server resolve
  3 partes cross-database e o `tabelas_referenciadas` ignora o catalog).
- [x] **Fase 0 · T9 (2026-07-20) — o último dos 3 defeitos reais:** introspecção por **query
  parameters**. Commit `bc8f901`. A regex `_IDENT`/`_validar_ident` saiu; `listar_tabelas`/
  `listar_views`/`descrever_tabela` mandam o nome por `%s`+`params`, matando a classe de injeção.
  **O plano estava errado (medido):** mandava **desligar o validador** quando `params is not None`,
  supondo `%s` não-parseável — mas `%s` parseia no sqlglot 30.12, passa `validar()` e `injetar_limit()`,
  então o cadeado nº 3 ficou **ligado em todo caminho**. −6 testes (7 da regex saíram, +1 de parâmetro).
  Prova e2e: payload de `DROP` vai por `params`, auditoria registra `%s`; `2fa_tokens` descreve sem erro.
- [ ] 🐛 **Recusa no `amostra` não vira auditoria** (a T9 fechou a metade irmã). Antes `amostra` **e**
  `descrever_tabela` recusavam nome inválido sem rastro; a T9 removeu o `_validar_ident`, então
  `descrever_tabela`/`listar_*` **não recusam mais na camada de transporte** (o nome vai por `params`).
  **Sobra o `amostra`:** `nucleo.dialeto.sql_amostra(tabela, n)` levanta `SqlInvalido` como argumento,
  ANTES do `nucleo.consultar`, e o `except McpDbError` do tool devolve `{"erro": ...}` **sem auditar**.
  Pré-existente, falha fechada, nada vaza — mas fura a propriedade nº 1. Remédio: descer a lógica do
  `amostra` pro `Nucleo` (converge com o item abaixo).
- [ ] 🧪 **As tools MCP são intestáveis sem banco** — o `construir_servidor` não tem ponto de
  injeção (`conectar=False` retorna **antes** de registrar as tools; `conectar=True` abre conexão
  real). É por isso que o `amostra` nunca teve teste unitário. **Remédio comum com o item acima:**
  descer a lógica das tools pro `Nucleo` — que é onde auditoria e testabilidade já moram, e é o que
  a docstring dele já promete ("independente do transporte MCP, testável isolado"). A T10 passou
  sem tocar nisto (foi refactor puro do doctor); vizinho natural da Fase 1 ou de um cleanup dedicado.
- [ ] **Teste de invariante por dialeto** (achado das revisões da T6; o remédio é um só pros dois):
  um teste genérico em `test_dialetos.py` que **todo dialeto futuro** tenha que satisfazer —
  (a) `sqlglot_dialeto` faz round-trip num `sqlglot.parse("SELECT 1", read=...)` e
  (b) `funcs_proibidas` **não é vazia**. Falha no CI em vez de na query. Ver os dois gotchas novos.
- [x] **Fase 0 · T10-T12 (2026-07-20):** doctor delega o probe (`sql_probe_escrita`/`erros_readonly`,
  commit `afe6812`) → fiação e2e `tests/test_ataques_e2e.py` (15 casos, `94535d0`) → docs + CHANGELOG
  0.3.0 + verificação final (`30ebd29`). Verificação final: 150/0 com banco, 126/24 sem, doctor 6/6,
  ruff/format/mypy limpos.
- [x] **Decidido (2026-07-16): os docs internos são públicos** — spec, plano, `CLAUDE.md` e
  `worklog.md` versionados. Backup off-machine vale mais que arrumação estética.
- [ ] **Revisão retroativa da Task 2** (o rename) — a formal nunca rodou.
- [ ] **Fase 1 (MySQL)** e **Fase 2 (SQL Server)** — cada uma com plano próprio, depois da 0 verde.
- [ ] **Escrita configurável** — spec próprio, quando chegar a hora. Ver o princípio acima.
- [ ] Dívida menor: `conn: Any` em `dialetos/postgres.py::_configurar/_resetar` — dá pra manter
  `psycopg.Connection` via `TYPE_CHECKING` e não perder a precisão de tipo.

## Pendências — auditoria 2026-07-17
### Erros / quebrado
- [x] ✅ **Resolvido 2026-07-20 (`30ebd29`):** `docs/DESIGN.md` não-objetivos — "outros SGBDs: nunca"
  virou "MySQL/SQL Server são fases 1 e 2"; escrita passou a "fora do escopo atual (spec próprio)".
- [x] ✅ **Resolvido 2026-07-20 (`30ebd29`):** `docs/03-arquitetura.md` (diagrama + tabela) e
  `docs/VISAO-GERAL.md` — `db.py` descrito como fachada fina que delega ao dialeto; nova linha de
  `dialetos/` na tabela de componentes.
- [ ] **A branch `main` (default do GitHub neste repo PÚBLICO) está 19 commits atrás** de
  `refactor/fase-0-multi-dialeto` (era 14 na auditoria; +5 nesta sessão). **Agora a Fase 0 fechou**,
  então já é seguro trazer `main` em dia — **decisão do Bruno**, junto do push dos 5 commits ainda
  não-pushados. Enquanto não for feito, quem visita o repo sem trocar de branch vê `pg-readonly-mcp`
  0.2.0 e o `except ParseError` já corrigido.
- [x] ✅ **Resolvido 2026-07-20 (`94535d0`, T11):** `tests/test_ataques_e2e.py` existe — 15 casos de
  fiação (12 ataques + SELECT legítimo + allowlist + auditoria), 15 passed com banco / 15 skipped sem.
- [x] ✅ **Resolvido 2026-07-20 (`bc8f901`, T9) — parcial:** o `_validar_ident` foi **removido**, então
  `descrever_tabela`/`listar_tabelas`/`listar_views` não estouram mais `ToolError` cru (o nome vai por
  `params`). **Sobra a irmã do `amostra`** (recusa sem auditoria) — movida pro Backlog como item vivo.

### Sugestões
- [x] ✅ **Resolvido 2026-07-20 (`30ebd29`):** `CHANGELOG.md` ganhou o entry `0.3.0` (rename BREAKING,
  arquitetura multi-dialeto, os 3 defeitos + o do `TokenError`).
- [ ] Todo commit do repo (o único público do portfólio) tem autor
  `bruno.outcore@guarida.com.br` — liga a identidade pública do GitHub ao empregador. Considerar
  `git config user.email` dedicado a este repo se a separação pessoal/Guarida importar.
- [x] ✅ **Resolvido 2026-07-20 (`bc8f901`, T9):** `db.py::executar` docstring — os callers de
  introspecção (`listar_tabelas`/`listar_views`/`descrever_tabela`) **passam `params` de verdade**
  agora; a docstring deixou de ser aspiracional.
