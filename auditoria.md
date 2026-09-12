# Auditoria — db-mcp — 2026-09-12
_Anel 1. Anterior: 2026-08-20. Governança 82/100 — Seg 22 · Cont 20 · Conx 19 · Hig 21._

## Veredito
Ferramenta MCP read-only para Postgres/MySQL/SQL Server, tecnicamente sólida: núcleo
dialeto-agnóstico, validador SQL por AST (não regex) testado contra corpus de ataque real, e
guarda-corpos de read-only medidos e documentados por dialeto — inclusive as diferenças honestas
(SQL Server não tem read-only de sessão; só o GRANT segura). O que impede de ser o que promete
não é o código, é a governança: a Fase 2 está pronta e verde há 53 dias numa branch que nunca
chegou ao `main`, e o repo é o único **público** do portfólio — quem visita hoje não vê o SQL
Server. No período desde a última auditoria (23 dias), houve exatamente **1 commit**, e era só
uma correção de frontmatter (`atividade: ativo→parado`). O projeto está genuinamente parado.

## 🔴 Crítico
Nenhum. Sem segredo vivo (histórico completo verificado), sem produção quebrada (não há
produção) e sem serviço fora do ar (não tem deployment — `no_ar: não` confere).

## 🟠 Importante
- [ ] **Merge de `refactor/fase-2-sqlserver` → `main` segue pendente.** Eram 21 commits de
  atraso em 08-20; hoje são **23** (`git log main..HEAD --oneline | wc -l`), 53 dias desde o
  último commit substantivo (2026-07-21). `git merge-base --is-ancestor refactor/fase-2-sqlserver
  main` confirma que **não** está incorporada. Repo público — quem visita o GitHub não vê o
  suporte a SQL Server apesar de a Fase 2 estar fechada e o CI estrutural bater (8 jobs: `lint` +
  matrix `test` 2 OS × 2 Python + `integration-postgres/mysql/sqlserver`, `.github/workflows/ci.yml`)
  — **não dá pra confirmar os *runs* daqui, só que o workflow existe com 8 jobs reais**.
- [ ] **`src/db_mcp/config.py:41`** — `statement_timeout_ms: int = 5000` sem `Field(gt=0)`.
  Confirmado ainda sem correção (mesmo achado de 08-20, agora 53 dias em aberto): `0`/negativo
  desliga o timeout em silêncio nos três dialetos (repassado cru em `postgres.py:118`,
  `mysql.py:85`, e no `sqlserver.py` via `_conectar`). Exige misconfiguração explícita do
  operador (o default 5000 é seguro), por isso fica em Importante e não em Crítico.

## 🟡 Melhoria
- [ ] Nenhum teste de regressão explícito para `CALL proc()` (Postgres/MySQL). Verificado nesta
  auditoria (parse direto com `sqlglot`, os três dialetos): `CALL` cai em `exp.Command`, que
  **já está** em `TAGS_PROIBIDAS` (`guardrails/sql.py:27`) — não é brecha, é lacuna de cobertura
  de teste (o corpus em `tests/test_ataques_e2e.py`/`test_sql.py` não tem o caso).
- [ ] `refactor/fase-0-multi-dialeto` (local+remoto) confirmada ancestral de `main`
  (`git merge-base --is-ancestor` ok) — peso morto, já no Backlog.
- [ ] Tags retroativas `v0.2.0`/`v0.3.0` — e agora também **`v0.5.0`**, já que a Fase 2 nunca foi
  taggeada por não estar em `main`. O CHANGELOG declara as quatro (`0.2.0`/`0.3.0`/`0.4.0`/`0.5.0`
  em `CHANGELOG.md`); só `v0.4.0` existe em `git tag`.
- [ ] Autor de 100% dos commits é `bruno.outcore@guarida.com.br` (confirmado via
  `git log --format='%ae' | sort -u`, 2 e-mails, o outro é pessoal) — expõe o domínio do
  empregador na identidade pública do GitHub. Já backlogado, baixa prioridade.

## 🧹 Higiene
- [ ] Sem `connections.md` (nem entrada em `_sistema/connections.md`) — **2ª auditoria seguida
  sem ação**. Risco prático baixo (a ferramenta não tem deployment real: só 3 containers de
  demo com credenciais fake), mas é o gap estrutural que mais pesa na nota de Conexões.
- [ ] Sem `decisions.md` (`worklog.md` cobre parte do papel, mas não é o mesmo artefato).
- [ ] O bloco antigo `## Pendências — auditoria 2026-08-20` duplicava ~4 dos 7 itens já abertos
  no `## Backlog` (merge pendente, `STATEMENT_TIMEOUT_MS`, apagar branch fase-0 — mesmo achado
  contado 2×), inflando a contagem para 13 itens abertos. Migrado para o Anexo abaixo; a partir
  de agora, pendência nova não deveria reafirmar o que já está no Backlog.
- [ ] `audit.log` (280 KB) e `audit-plusoft.log` (194 KB, crescendo — eram 173 KB/18 KB em
  08-20) seguem no working directory, corretamente git-ignorados. Não li o conteúdo (fora de
  escopo, e o segundo nome sugere dado de outro projeto/cliente vazando pro diretório de
  trabalho compartilhado) — só reconfirmando a nota já existente, agora com o dado de que os
  arquivos continuam crescendo.

## Objetivo × entregue (~90%)
**Pronto:** núcleo dialeto-agnóstico (Postgres/MySQL/SQL Server, `dialetos/base.py` +
`_REGISTRO`) · validador SQL por AST (`guardrails/sql.py`, `sqlglot`) bloqueando
INSERT/UPDATE/DELETE/DDL/CTE-que-escreve/múltiplas instruções — testado contra corpus real
(`test_cte_que_escreve_e_bloqueada`, `test_multiplas_instrucoes_bloqueadas`,
`test_ataques_e2e.py`) · allowlist com invariante anti-cross-database catalog-aware
(`guardrails/policy.py:69-87`) · `injetar_limit` sempre reemite via AST no dialeto alvo
(`policy.py:106-133`) · read-only reforçado e MEDIDO por dialeto: `conn.read_only = True` no
Postgres (`postgres.py:132`), `SET SESSION TRANSACTION READ ONLY` reaplicado a cada checkout no
MySQL por causa do bug do `pool_reset_session` (`mysql.py:84`, guardado por
`test_mysql_reaplica_read_only_a_cada_checkout`), e no SQL Server a ausência honesta de
read-only de sessão documentada (`SET TRANSACTION READ ONLY` → erro 156) com conexão nova por
consulta como mitigação · demos com usuários `GRANT SELECT`-only nos 3 bancos
(`demo/init*/03-mcp-ro.sql`) · CI com 8 jobs reais incluindo 3 integrações contra bancos vivos
em container · `doctor` com 6 checagens por dialeto.
**Falta:** merge pra `main` (repo público ainda mostra só até MySQL/`v0.4.0`) · escrita
configurável (spec própria, propositalmente fora de escopo agora) · `connections.md`/
`decisions.md` consolidados · tags retroativas.
**Quebrado:** `src/db_mcp/config.py:41` — `statement_timeout_ms` sem validação, `0`/negativo
desliga o timeout em silêncio.

## Doc contra realidade
- **Achado positivo, incomum:** o `CLAUDE.md` está genuinamente alinhado com o git — não uma
  vitrine. A única contradição real do período (frontmatter `atividade: ativo` enquanto o
  projeto já estava parado desde 07-21) **já tinha sido autocorrigida em 2026-09-09** (commit
  `e4dc697`), antes desta auditoria começar.
- A alegação **"CI 8/8"** é estruturalmente verificável (o workflow existe com exatamente 8 jobs:
  `lint`, `test`×4 matriz, `integration-postgres/mysql/sqlserver`) — mas o resultado real dos
  *runs* não é visível daqui (sem acesso à API do GitHub Actions neste modo); a auditoria
  confirma a estrutura, não a execução.
- `CHANGELOG.md` declara `v0.2.0`/`v0.3.0`/`v0.5.0` que não existem como tags no git (só
  `v0.4.0`) — já era conhecido, confirmado ainda verdadeiro.
- Backlog "13 itens abertos" (confirmado batendo com o snapshot automatizado) infla por
  duplicação entre `## Backlog` e `## Pendências — auditoria 2026-08-20` (ver 🧹 acima) — não é
  item fossilizado nem já feito, é dupla contagem do mesmo achado.

## §0 — achados anteriores resolvidos/refutados
Nenhum. Zero commits de código desde 2026-08-20 (só 1 commit de doc, frontmatter). Todos os
achados da auditoria anterior seguem abertos — reafirmados acima com números atualizados
(21→23 commits de atraso; `audit.log` 173→280 KB).

## Cobertura da leitura
**Lido a fundo (linha a linha):** `src/db_mcp/guardrails/sql.py` (82 linhas, completo) ·
`src/db_mcp/guardrails/policy.py` (134 linhas, completo) · `.gitignore` (completo) ·
`CLAUDE.md` (completo) · trechos de `tests/test_sql.py`, `test_ataques_e2e.py`,
`test_sql_mysql.py`, `test_sql_sqlserver.py`, `test_db_integration.py` (os casos de ataque e o
gate de skip) · fluxo `server.py`→`db.py` (ordem validar→allowlist→limit→executar) ·
`demo/init*/03-mcp-ro.sql` (linhas de GRANT) · `.github/workflows/ci.yml` (jobs e matrix).

**Amostrado (grep/trechos):** `README.md`, `docs/DESIGN.md`, `docs/00-para-leigos.md`,
`docs/01-instalacao.md`, `docs/02-preparar-o-banco.md`, `docs/04-troubleshooting.md`,
`SETUP.md`, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md` (só headers), `worklog.md` (tail) ·
`dialetos/postgres.py`, `mysql.py`, `sqlserver.py` (só as linhas de read-only/timeout) ·
`config.py` (só o campo do timeout) · `.claude/skills/setup-db-mcp/SKILL.md` · histórico git
completo (`git log --all -p -S 'password'`, `--diff-filter=A --name-only`, 78 commits).

**Não aberto:** `src/db_mcp/cli.py`, `errors.py`, `observability.py`,
`guardrails/ratelimit.py`, `dialetos/__init__.py`, `dialetos/base.py` (só referenciados) ·
`tests/test_cli.py`, `test_config.py`, `test_dialetos.py`, `test_doctor.py`,
`test_doctor_integration.py`, `test_e2e_integration.py`, `test_errors.py`,
`test_observability.py`, `test_policy.py`, `test_ratelimit.py`, `test_server.py` ·
`docs/superpowers/plans/*.md`, `docs/superpowers/specs/*.md` · `deployments/README.md` ·
`config.example.yaml`, `.env.example`, `docker-compose.yml` (além das linhas já grepadas) ·
conteúdo de `audit.log`/`audit-plusoft.log` (deliberadamente, ver 🧹 acima).

## Anexo — bloco anterior migrado do CLAUDE.md (auditoria de 2026-08-20)
### Pendências — auditoria 2026-08-20
Verificado contra git + código real (não só docs). Segurança: **limpa** — nenhum segredo vivo
no histórico completo (76 commits, `git log --all -p` sem hit real), demo creds são fake e
rotuladas, `.gitignore` cobre `.env*`/`config.yaml`/`deployments/*`/`*.log`, e o GitHub confirma
`private: false` (repo é mesmo público). As três fases (multi-dialeto, MySQL, SQL Server) batem
com o código: núcleo dialeto-agnóstico confirmado em `dialetos/base.py`, o fix do
`injetar_limit` (T6) confirmado em `guardrails/policy.py:115-133`, os dois fixes do `doctor.py`
(`SELECT 1 AS um`, fallback de `.sqlstate`) confirmados em `doctor.py:268-353`, CI verde
confirmado via API do GitHub no commit `c9e5f27` (HEAD da branch).

#### Erros / quebrado
- `config.py:41` — `statement_timeout_ms: int = 5000` sem `Field(gt=0)`; `0`/negativo
  desliga o timeout em silêncio nos três dialetos (repassado cru em `postgres.py:118` via
  `options=f"-c statement_timeout={s.statement_timeout_ms}"` e em `mysql.py:85` via
  `SET SESSION max_execution_time = {int(self._timeout_ms)}`). Já é backlog conhecido — só
  confirmando que segue sem correção.
- `main` (`2817312`/`v0.4.0`) está **21 commits atrás** de `refactor/fase-2-sqlserver`
  (`__version__ 0.5.0`), parada desde 2026-07-21 — **exatos 30 dias sem merge**
  (`git merge-base --is-ancestor` confirma que main NÃO tem a branch). Repo é público: quem
  visita o GitHub hoje não vê o suporte a SQL Server, apesar de a Fase 2 estar fechada e verde.

#### Sugestões
- Decidir o merge de `refactor/fase-2-sqlserver` → `main` (tag `v0.5.0`) — já é a
  próxima ação declarada há 30 dias; o adiamento cresce o drift num repo público.
- Apagar `refactor/fase-0-multi-dialeto` (local+remoto) — já incorporada ao main, é peso
  morto (item já no Backlog).
- Não existe `connections.md`; o equivalente vive espalhado em "Ambiente & acessos" +
  `deployments/README.md`. Funciona para uma ferramenta sem deployment real, mas não há um
  ponteiro único — considerar consolidar se o projeto ganhar um ambiente real registrado.
- `audit.log` (173KB) e `audit-plusoft.log` (18KB, datado de hoje) existem no working
  directory, corretamente git-ignorados (`*.log`) — não é achado de segurança, só nota: como
  o diretório de trabalho é compartilhado entre sessões, confirmar que não guardam dado de
  cliente antes de qualquer mudança futura no `.gitignore`.
