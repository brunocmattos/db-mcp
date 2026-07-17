# Worklog — db-mcp

## 2026-07-16 · Manutenção — Fase 0, Task 6: o validador recebe o dialeto
**O quê:** a sessão abriu com uma dúvida ("não sei se to abrindo na branch certa" — estava certa:
`refactor/fase-0-multi-dialeto`) e seguiu pra **Task 6** do plano da Fase 0.   ·   **Objetivo:**
`guardrails/sql.py` vira `validar(sql, dialeto, perfil)`, a lista de funções proibidas passa a vir
do dialeto e `test_sql.py` fica parametrizado — com a suíte verde e **zero mudança de comportamento**.

**Feito:**
- **Task 6 fechada — commit `7c39ada`.** `validar_somente_leitura(sql)` → `validar(sql, dialeto,
  perfil)`; o parse agora usa `dialeto.sqlglot_dialeto` (era `read="postgres"` hardcoded) e a
  blocklist vem de `dialeto.funcs_proibidas`. `TAGS_PROIBIDAS` **ficou** no módulo, de propósito.
  `test_sql.py` parametrizado via `_validar_pg` sobre `PG = obter_dialeto("postgres")` — é a
  estrutura que as Fases 1 e 2 reusam (cada uma acrescenta a sua tabela de ataques; os corpora
  **não** são compartilhados: `pg_read_file` não existe no MySQL, `load_file` não existe no Postgres).
- **Verificação antes de executar, não depois:** medi que `FUNCS_PROIBIDAS` (sql.py) e
  `FUNCS_PROIBIDAS_POSTGRES` (postgres.py) tinham as **mesmas 50 funções**, zero diferença nos dois
  sentidos — só por isso remover a do módulo era seguro. Baseline `test_sql.py` = **45 testes**, e
  45 continuam passando (se tivesse ficado verde com menos, alguém teria apagado ataque).
  118 passed / 9 skipped, ruff + format + mypy limpos.
- **Duas revisões, as duas passaram.** Spec: conformidade total. Qualidade: **zero Critical, nada
  bloqueando** — mas dois achados reais, ambos armadilhas de Fase 1/2, agora no Backlog e nos
  Gotchas (a confusão `sqlserver`/`tsql` e o `funcs_proibidas` vazio).
- **Desvio do plano, registrado:** o implementador teve que tocar `tests/test_server.py`, que o plano
  não previa — os fakes precisaram de `.dialeto` porque o `Nucleo.__init__` do próprio plano exige.
  Revisado e liberado (16 testes antes e depois; usar o `DialetoPostgres` real nos fakes mantém o
  validador idêntico ao de produção, em vez de deixá-los mais permissivos). É lacuna do plano.

**Riscos / quem afeta:** ⚠️ **Nada em produção** — o projeto segue sem deployment. ⚠️ **2 commits
locais sem push** ao fechar (`4c45c0c` da auditoria + `7c39ada` da T6) — trabalho num disco só até
subirem. 📌 **Uma auditoria (`/portfolio-audit`) rodou em paralelo nesta mesma branch** (commit
`4c45c0c`, 14:43) e deixou a seção `## Pendências — auditoria 2026-07-16` no `CLAUDE.md`; o item dela
sobre `sql.py:108` **já nasceu vencido** — a T6 o corrigiu 5 minutos depois, e o item foi marcado
como resolvido para o próximo `/abrir` não ler pendência falsa. A parte viva (`policy.py:28,77`) é
a T7. 📌 A auditoria também nota que todo commit deste repo (o único **público**) leva o e-mail
`@guarida.com.br` — decisão pendente do Bruno, não é bug.

**Próximo:** **Task 7** — `injetar_limit` emite no dialeto alvo (`dialect="postgres"` hardcoded em
`guardrails/policy.py` faria `TOP 9999` virar `LIMIT 1000`). Depois **T8** (`amostra` usa
`sql_amostra`) e **T9** (introspecção por query parameters), então **T10-T12** (doctor, teste de
fiação e2e, docs + verificação final).

## 2026-07-16 · Design + desenvolvimento — o projeto virou multi-dialeto (Fase 0, T1-T5)
**O quê:** o projeto entrou no portfólio e recebeu o pedido de suportar **MySQL e SQL Server** além
do PostgreSQL.   ·   **Objetivo:** decidir a arquitetura multi-dialeto, escrever spec e plano, e
executar a Fase 0 (refatorar **sem** adicionar dialeto novo).

**Feito:**
- **Auditoria de entrada do código** (antes de qualquer mudança): 119 testes verdes, `ruff` e
  `mypy --strict` limpos, `doctor` **6/6** contra o demo Docker — a saída bate **exatamente** com a
  prometida no README, incluindo o `25006 ReadOnlySqlTransaction`. Probe adversarial próprio: **15/15
  ataques barrados**, e a análise de escopo do sqlglot acerta o auto-sombreamento de CTE
  (`WITH pedidos AS (SELECT * FROM pedidos)` → barra, porque o `pedidos` de dentro é a tabela real).
- **Portabilidade MEDIDA, não presumida** (sqlglot 30.12): os nós de escrita têm nome **idêntico**
  nos 3 dialetos, `exp.Anonymous` pega função perigosa nos 3, e `LIMIT` vira `TOP` sozinho no tsql.
  **Conclusão que definiu o design: muda a LISTA de funções, não o mecanismo** → o núcleo já era
  dialeto-agnóstico, e o que varia cabe num contrato de 11 membros.
- **[Spec aprovado](docs/superpowers/specs/2026-07-16-db-mcp-multi-dialeto-design.md)** — decisões:
  **um repo** com dialetos como módulos (3 repos fariam a lista de funções perigosas divergir) ·
  **pool nativo por dialeto** (`DBUtils` não roda `DISCARD ALL`, que é segurança; SQLAlchemy é dep
  grande demais) · **pymssql** (pyodbc exige `msodbcsql18` no SO) · **mysql-connector** (tem pool +
  `RESET CONNECTION`) · **só leitura** — escrita ganha spec próprio. Repo renomeado
  `pg-readonly-mcp` → **`db-mcp`** (a URL antiga redireciona).
- **[Plano da Fase 0](docs/superpowers/plans/2026-07-16-db-mcp-fase-0-multi-dialeto.md)** (12 tasks,
  TDD). **T1-T5 executadas, commits `52bd464..8864f69`:** pasta+remote → pacote `db_mcp` e comando
  `db-mcp` → config `dialeto` + `--dialect` → contrato `Dialeto` + `dialetos/postgres.py` → **`db.py`
  delega** (o `psycopg` saiu do núcleo). **127 passed / zero skipped** contra o Postgres vivo; o
  `DISCARD ALL` migrou byte-idêntico (verificado, é segurança e não higiene).
- **3 defeitos achados testando** (só se manifestariam em produção no SQL Server): `injetar_limit`
  com `dialect="postgres"` hardcoded · `amostra` montando `LIMIT` na mão e escapando da transpilação ·
  `_validar_ident` com regex de Postgres. Correção do 3º refinada no plano: são **dois** problemas em
  posições SQL diferentes (literal → query parameter; identificador → quoting via sqlglot).

**Riscos / quem afeta:** ⚠️ **Nada em produção** — o projeto não tem deployment; o único banco tocado
foi o container de demo. ✅ **Pushado** (`main` + `refactor/fase-0-multi-dialeto`) — o trabalho deixou
de existir num disco só. 📖 **Decidido: os docs internos são públicos** (spec, plano, `CLAUDE.md`,
`worklog.md`). O repo é o único público do portfólio; git-ignorá-los compraria arrumação estética
pagando com a falha que a auditoria aponta há 6 rodadas — trabalho sem backup off-machine. Segredo
nenhum entra aqui: `.env`/`config.yaml`/`deployments/` seguem git-ignored. ⚠️ **A Task 2 (rename) não passou pela
revisão formal** — os dois revisores falharam (defeito + limite de sessão da API); está de pé por
aprovação do Bruno + verificação manual. 📌 **Registrado como dívida:** a flag `--dialect` não alcança
o `doctor`; inofensivo hoje, mente em silêncio a partir da Fase 1 (marcador `# FASE 1:` no `cli.py`).

**Próximo:** **Task 6** — `validar(sql, dialeto, perfil)`, `FUNCS_PROIBIDAS` vindo do dialeto e
`test_sql.py` parametrizado (é a estrutura que as Fases 1 e 2 reusam) → **T7-T9** (os 3 defeitos) →
**T10-T12** (doctor, teste de fiação e2e, docs + verificação final: `doctor` 6/6 e suíte verde).
Fases 1 (MySQL) e 2 (SQL Server) só depois da 0 fechada — cada uma com plano próprio.
