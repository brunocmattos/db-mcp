# Worklog — db-mcp

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
foi o container de demo. ⚠️ **Nada pushado** (5 commits na branch `refactor/fase-0-multi-dialeto`) —
**o GitHub é o único backup off-machine e ele ainda não tem nada disto.** ❓ **Bloqueia o 1º push:**
decidir se `docs/superpowers/` vai pro repo **público**. ⚠️ **A Task 2 (rename) não passou pela
revisão formal** — os dois revisores falharam (defeito + limite de sessão da API); está de pé por
aprovação do Bruno + verificação manual. 📌 **Registrado como dívida:** a flag `--dialect` não alcança
o `doctor`; inofensivo hoje, mente em silêncio a partir da Fase 1 (marcador `# FASE 1:` no `cli.py`).

**Próximo:** **Task 6** — `validar(sql, dialeto, perfil)`, `FUNCS_PROIBIDAS` vindo do dialeto e
`test_sql.py` parametrizado (é a estrutura que as Fases 1 e 2 reusam) → **T7-T9** (os 3 defeitos) →
**T10-T12** (doctor, teste de fiação e2e, docs + verificação final: `doctor` 6/6 e suíte verde).
Fases 1 (MySQL) e 2 (SQL Server) só depois da 0 fechada — cada uma com plano próprio.
