---
tipo: projeto
cliente: interno
produto: —
no_ar: não
atividade: ativo
stack: ["Python 3.11+", "uv", "FastMCP", "psycopg3", "sqlglot"]
ultima_atividade: 2026-07-16
proxima_acao: "Fase 0 · Task 6: validador recebe o dialeto"
repo: git+remote
tags: [mcp, banco-de-dados, open-source, postgres]
---
# db-mcp

## Estado atual
**Fase 0 em andamento — refatorar para multi-dialeto, ainda só com PostgreSQL.**
Branch `refactor/fase-0-multi-dialeto`, **5 commits, nada pushado**. Tasks 1-5 feitas, **6-12 faltam**.

- 📄 **[Spec do design multi-dialeto](docs/superpowers/specs/2026-07-16-db-mcp-multi-dialeto-design.md)**
  (aprovado) e **[plano da Fase 0 (12 tasks)](docs/superpowers/plans/2026-07-16-db-mcp-fase-0-multi-dialeto.md)**.
  Fases 1 (MySQL) e 2 (SQL Server) ganham planos próprios quando a 0 fechar.
- ✅ **O marco da fase já caiu:** o `db.py` **não importa mais `psycopg`** — pool, cursor-dict e
  tradução de exceção do driver vêm do contrato `Dialeto`. O núcleo ficou dialeto-agnóstico.
- 🧪 **Testes:** 118 passed sem banco · **127 passed / zero skipped** com o demo Docker de pé.
  A Fase 0 não muda comportamento: a suíte existente É a rede de segurança.
- ⚠️ **A Task 2 (rename) nunca passou pela revisão formal** — os dois revisores falharam (um deu
  defeito, o outro bateu no limite de sessão da API). Está de pé por aprovação do Bruno + verificação
  manual (110/9 idêntico à base, zero ocorrência do nome antigo, `docs/superpowers/` intacto).
  Revisão retroativa está no Backlog.
- ❓ **Decisão aberta:** `docs/superpowers/` (spec + plano) vai pro repo **público** ou entra no
  `.gitignore`? O `.gitignore` já mantém `docs/plans/` e `docs/HANDOFF.md` fora, mas não cobre
  `docs/superpowers/`. Nada pushado ainda — dá tempo de decidir.

**Próxima ação:** **Task 6** — `guardrails/sql.py` vira `validar(sql, dialeto, perfil)`; a lista de
funções proibidas sai do módulo e passa a vir do dialeto, e `test_sql.py` fica parametrizado por
dialeto (é a estrutura que as Fases 1 e 2 reusam).

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
uv run pytest -q                         # 118 passed, 9 skipped (integração se auto-pula sem banco)
# com banco (destrava os 9 de integração → 127 passed, zero skipped):
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
- **A allowlist é defesa em profundidade, não o limite último.** O isolamento forte tem que estar no
  banco (GRANT só nas tabelas certas). Ver `docs/DESIGN.md §5` — ele é honesto sobre o que a análise
  de SQL **não** cobre.

## Backlog
- [x] **Fase 0 · T1-T5 (2026-07-16):** pasta/remote → pacote `db_mcp` + comando `db-mcp` → config
  `dialeto` + `--dialect` → contrato `Dialeto` + `dialetos/postgres.py` → `db.py` delega.
  Commits `52bd464..8864f69`. **127 passed / zero skipped** contra o Postgres vivo.
- [ ] **Fase 0 · T6 (próximo):** `validar(sql, dialeto, perfil)`; `FUNCS_PROIBIDAS` sai do módulo e
  vem do dialeto (`TAGS_PROIBIDAS` fica — os nós são idênticos nos 3); `test_sql.py` parametrizado.
- [ ] **Fase 0 · T7-T9 — os 3 defeitos reais** (só se manifestam no SQL Server, mas a costura é aqui):
  **T7** `injetar_limit` emite no dialeto alvo (`dialect="postgres"` hardcoded faria `TOP 9999` virar
  `LIMIT 1000`) · **T8** `amostra` usa `sql_amostra` do dialeto (montava `LIMIT` na mão e escapava da
  transpilação) · **T9** introspecção por **query parameters** (a regex `_IDENT` era de Postgres —
  rejeitava `2fa_tokens`, aprovava `Order`; parâmetro mata a classe de injeção em vez de filtrá-la).
- [ ] **Fase 0 · T10-T12:** doctor delega o probe de escrita → teste de **fiação** e2e (os unitários
  provam que o validador está correto; falta provar que está **plugado**) → docs + verificação final.
- [ ] **Decidir: `docs/superpowers/` vai pro repo público ou pro `.gitignore`?** Bloqueia o 1º push.
- [ ] **Revisão retroativa da Task 2** (o rename) — a formal nunca rodou.
- [ ] **Fase 1 (MySQL)** e **Fase 2 (SQL Server)** — cada uma com plano próprio, depois da 0 verde.
- [ ] **Escrita configurável** — spec próprio, quando chegar a hora. Ver o princípio acima.
- [ ] Dívida menor: `conn: Any` em `dialetos/postgres.py::_configurar/_resetar` — dá pra manter
  `psycopg.Connection` via `TYPE_CHECKING` e não perder a precisão de tipo.
