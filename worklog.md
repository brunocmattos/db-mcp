# Worklog — db-mcp

## 2026-07-20 · Manutenção — Lacunas pós-Fase-0 fechadas + caça adversarial
**O quê:** com a Fase 0 fechada e pushada, fechar as lacunas que sobraram no Backlog antes de
mergear `main` e começar a Fase 1.   ·   **Objetivo:** `amostra` recusa com auditoria; teste de
invariante por dialeto; e confirmar que não há OUTRAS recusas sem auditoria.

**Feito:**
- **🐛 Lacuna do `amostra` fechada — commit `bc2a20b`.** A lógica desceu pro `Nucleo.amostrar`: o
  build `sql_amostra` (que levantava `SqlInvalido` como argumento, ANTES do `Nucleo.consultar`, e
  saía sem trilha) agora roda DENTRO da trilha auditada. Nome inválido audita `veredito=sql_invalido`
  com o nome tentado (valor forense) e re-levanta; a tool traduz pra `{"erro": ...}`. **Provado e2e
  contra o demo:** 2/2 sondagens auditam (antes 1/2). De quebra, o `amostra` — única tool com lógica
  fora do Nucleo — ficou testável sem banco. +3 testes unitários.
- **🧪 Teste de invariante por dialeto — commit `cc20676`.** `dialetos/__init__.py` ganhou um
  `_REGISTRO` de fábricas lazy como **fonte única**; `DIALETOS_IMPLEMENTADOS` deriva dele e
  parametriza o `test_invariante_todo_dialeto`, que exige de TODO dialeto futuro: (a) `sqlglot_dialeto`
  faz round-trip real (pega `"sqlserver"` no lugar de `"tsql"`) e (b) `funcs_proibidas` não-vazia.
  Fecha no CI os dois gotchas nº 1 e nº 2 do CLAUDE.md.
- **🔍 Caça adversarial (workflow, 3 finders + verificação que refuta):** 7 candidatos → **1
  confirmado, 1 já-corrigido, 5 refutados**. O confirmado é o gotcha nº 1 (`ValueError` de
  `sqlglot_dialeto` inválido escapa do `except SqlglotError`/`except McpDbError`) — mas **inalcançável
  hoje** (só `postgres` resolve, `sqlglot_dialeto='postgres'` é válido; nome errado derruba o servidor
  no boot) e **agora guardado no CI** pelo teste de invariante acima. Refutados verificados: o
  `PoolTimeout` foi MEDIDO tendo `psycopg.Error` na MRO (é embrulhado e auditado); `json.dumps` não é
  recusa (McpDbError); a camada de tool está limpa (T9 + amostra). **Zero recusas alcançáveis sem
  auditoria hoje.**
- **Decisão registrada:** **não** embrulhar `ValueError` no `validar()` — rotularia erro de config
  como recusa `SqlInvalido` do usuário (arquiteturalmente errado) e violaria YAGNI. O teste de
  invariante é o guard certo, na camada certa (CI).
- **Verificação:** 130/24 sem banco · **154/0 com o demo** · ruff/format/mypy limpos.

**Riscos / quem afeta:** ⚠️ **Nada em produção.** ⚠️ Commits pendentes de push/merge (`bc2a20b`,
`cc20676` + este de docs) — decisão do Bruno; repo PÚBLICO. Sem lacuna de auditoria alcançável
conhecida.

**Próximo:** push + merge/ff de `main` (autorizado). Depois **Fase 1 (MySQL)** com plano próprio —
**ler o plano com desconfiança** (o da Fase 0 errou em T7, T8 e T9).

## 2026-07-20 · Manutenção — Fase 0 FECHADA (T9→T12)
**O quê:** a sessão abriu perguntando o que faltava pra concluir a Fase 0 e seguiu executando as
**4 tasks finais** (T9, T10, T11, T12).   ·   **Objetivo:** fechar a Fase 0 multi-dialeto com a
suíte verde, zero mudança de comportamento no Postgres, e a Definição de Pronto batida.

**Feito:**
- **T9 — commit `bc8f901`.** Introspecção por **query parameters**. `listar_tabelas`/`listar_views`/
  `descrever_tabela` passaram a mandar o nome por `%s`+`params`; a regex `_IDENT`/`_validar_ident`
  saiu. TDD: RED visto falhar (`unexpected keyword argument 'params'`) → GREEN. **O plano errou de
  novo, e foi medido, não contornado:** ele mandava DESLIGAR o validador quando `params is not None`,
  supondo `%s` não-parseável — mas medi no sqlglot 30.12 que `%s` parseia, passa `validar()` e
  `injetar_limit()`, então o cadeado nº 3 ficou **ligado em todo caminho** (a versão do plano abriria
  um buraco de segurança à toa). −6 testes (7 da regex saíram, +1 de parâmetro). Prova e2e dirigida:
  payload `public'; DROP TABLE clientes --` → `[]` sem crash, auditoria registra `%s` (não o payload),
  `2fa_tokens` descreve sem `SqlInvalido`.
- **T10 — commit `afe6812`.** `doctor.checar_somente_leitura` delega `sql_probe_escrita()` e
  `erros_readonly` ao dialeto (a costura já existia no contrato). Refactor sem mudança de
  comportamento: doctor 6/6 com `write recusado: 25006 ReadOnlySqlTransaction` idêntico. `import
  psycopg` fica (o `checar_auth` ainda usa).
- **T11 — commit `94535d0`.** `tests/test_ataques_e2e.py`: 15 casos que provam que os guardrails
  estão **plugados** no caminho `Nucleo.consultar → guardrails → pool → banco` (os unitários provam
  correção; estes provam fiação). 15 passed com banco, 15 skipped sem.
- **T12 — commit `30ebd29`.** Docs sincronizados com honestidade: `DESIGN.md`/`VISAO-GERAL.md`
  não-objetivos (SGBDs não são "nunca", são fases 1 e 2); `03-arquitetura.md`/`VISAO-GERAL.md`
  (`db.py` virou fachada, pool vem do dialeto); README com nota de estado atual **sem** a tabela de
  cadeados por dialeto (documentar capacidade inexistente seria mentira); `CHANGELOG.md` entry 0.3.0.
- **Verificação final da fase (demo recriado do zero):** ruff/format/mypy limpos · 126/24 sem banco ·
  **150/0 com banco** · **doctor 6/6**. Definição de Pronto batida: os 3 defeitos com teste de
  regressão, `dialetos/base.py` sem driver, zero funcionalidade nova, nome antigo só em refs históricas.

**Riscos / quem afeta:** ⚠️ **Nada em produção** — sem deployment, só o demo Docker. ⚠️ **5 commits
NÃO-pushados** (T9-T12 + o de auditoria de 17/07) num repo **PÚBLICO**; push e merge de `main` (19
commits atrás) são **decisão do Bruno**, deixados pendentes de propósito (outward-facing). 🐛 **Lacuna
viva no Backlog:** `amostra` com nome inválido recusa **sem auditoria** (o `sql_amostra` levanta antes
do `Nucleo.consultar`); a T9 fechou a irmã da `descrever_tabela` ao remover o `_validar_ident`, mas a
do `amostra` sobrou. Falha fechada, nada vaza. 📌 O container `db-mcp-demo` ficou **de pé**.

**Próximo:** **decisão do Bruno** — push dos 5 commits + merge/fast-forward de `main`. Depois **Fase 1
(MySQL)** com plano próprio (ou fechar antes a lacuna do `amostra` + o teste de invariante por dialeto,
ambos no Backlog). E **ler o plano da Fase 1 com desconfiança** — o da Fase 0 errou em T7, T8 e T9.

## 2026-07-17 · Manutenção — Fase 0, T7 e T8 (e um defeito vivo que não estava no plano)
**O quê:** a sessão abriu para a **Task 7** e emendou a **Task 8**.   ·   **Objetivo:** os defeitos
5.1 e 5.2 do spec — `policy.py` e `amostra` param de cravar Postgres — com a suíte verde e **zero
mudança de comportamento** no Postgres.

**Feito:**
- **T7 — commit `646ba6b`.** `policy.py` lê e emite no dialeto alvo. **Desvio do plano, aprovado
  pelo Bruno:** `tabelas_referenciadas`/`checar_allowlist` ficaram com o dialeto **obrigatório**, sem
  o default `"postgres"` do plano (o default existia só pra poupar edição de teste, num caminho de
  segurança). Dividendo na hora: o mypy acusou os 2 callers do `server.py` — falha no CI, não na
  query. Os 19 testes existentes passaram **sem mudar uma expectativa** (verificado no diff: toda
  assertion removida tem contrapartida idêntica + `, PG`).
- **🐛 O achado da sessão — commit `74aba49`, fora do plano.** Revisando a T8 medi que `TokenError`
  **não é subclasse de `ParseError`** (são irmãs sob `SqlglotError`). O `except ParseError` do
  validador — cadeado nº 3(a) — deixava vazar recusa por aspa não fechada: não virava `SqlInvalido`,
  escapava do `except McpDbError` do `server.py` e **saía sem auditoria**. Alcançável por qualquer
  cliente na config padrão (`allow_freeform_sql=True`). Medido no caminho real do `Nucleo`: **1 de 3
  recusas auditadas antes, 3 de 3 depois.** Falhava fechado (nada vazava), mas furava a propriedade
  que o projeto declara a mais importante.
- **T8 — commit `67b6485`.** `amostra` delega ao dialeto. O `_validar_qualificado` **saiu** (ficou
  sem caller; o parse `into=exp.Table` é defesa mais estrita) e seu corpus de ataques foi
  **re-apontado** pro `sql_amostra`: de 4 pra 8 casos, nenhum perdido. **Fiação provada no servidor
  real** contra o demo: o SQL auditado saiu `SELECT * FROM "clientes" LIMIT 2` — a aspa é a
  assinatura do dialeto, a f-string antiga não a produziria.
- **O plano estava errado nos detalhes nas duas tasks, e isso foi registrado, não contornado:** a T7
  descrevia o defeito ao contrário (`TOP 9999` → `LIMIT 1000` **não** acontecia — dava `ParseError`;
  o caso real era a query T-SQL **sem** limite, que saía com `LIMIT` grudado); a T8 prescrevia um
  teste **tautológico** (re-testava o `sql_amostra`, já coberto em `test_dialetos.py:29`, sem tocar
  na mudança) e mandava escrever `except ParseError` — replicando o bug acima num segundo lugar.
- **Verificação:** 141 passed / **zero skipped** com o demo (eram 127 ao abrir) · 132/9 sem banco ·
  `doctor` 6/6 · ruff, format e mypy limpos · os 7 casos do Postgres no `injetar_limit` saem
  idênticos aos de antes.

**Riscos / quem afeta:** ⚠️ **Nada em produção** — segue sem deployment; o único consumidor é o demo
Docker. ✅ **Tudo pushado** (3 commits) e working tree limpo. 🐛 **Lacuna aberta, no Backlog:** recusa
na camada de transporte **não vira auditoria** — medido: `amostra` com nome injetado devolve erro
limpo mas **sem rastro**, e `descrever_tabela` com ident inválido **estoura `ToolError` cru**. É
pré-existente (verificado no código anterior à T8), não regressão. Converge com a outra lacuna: as
tools são **intestáveis sem banco** (sem ponto de injeção no `construir_servidor`) — um movimento só
resolve as duas, descendo a lógica pro `Nucleo`. 📌 O container `db-mcp-demo` ficou **de pé**.

**Próximo:** **Task 9** — introspecção por **query parameters**. Vale avaliar juntar com a lacuna de
auditoria das tools: a T9 mexe exatamente no `_validar_ident`, que é uma das validações que hoje
recusam sem deixar rastro. Depois **T10-T12** (doctor, fiação e2e, docs + verificação final). E
**ler o plano com desconfiança** — ele errou nas duas tasks desta sessão.

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
