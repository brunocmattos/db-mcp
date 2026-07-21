# Plano — Fase 1: dialeto MySQL

> **Spec:** [`2026-07-16-db-mcp-multi-dialeto-design.md`](../specs/2026-07-16-db-mcp-multi-dialeto-design.md)
> (§4 cadeados por dialeto, §5.4 funcs por dialeto, §6 schema==database, §8 fases, §9 testes/CI).
> **Pré-requisito:** Fase 0 fechada (12 tasks + lacunas pós-fase + merge de `main`). O núcleo já é
> dialeto-agnóstico; o `_REGISTRO` (`dialetos/__init__.py`) é a fonte única, e o
> `test_invariante_todo_dialeto` já é o gate de CI que **todo dialeto novo tem que passar**.

## Princípio da fase (o mesmo da 0, adaptado)
A Fase 1 **acrescenta** um dialeto. Não muda comportamento no Postgres — **a suíte existente é a
rede de segurança**. Cada mudança de contrato (`base.py`) é **atômica com o `postgres.py`**: emendar
o `Protocol` sem implementar no Postgres no mesmo commit = `AttributeError` em runtime (o mypy às
vezes deixa passar atributo-como-método em `Protocol`).

**Regra dos testes:** o total **só sobe**. Cada task diz quantos **acrescenta**. Os testes do
Postgres não podem mudar de expectativa (se mudaram, é regressão, não refactor).

## Tudo aqui foi MEDIDO, não presumido (grounding de 2026-07-20)
Uma pesquisa de 4 dimensões mediu o sqlglot 30.12 e leu o código/docs. Os fatos que fundam o plano:

- ✅ **O mecanismo do validador é dialeto-agnóstico no MySQL** (medido): o corpus de ataque inteiro
  (`UPDATE`/`CREATE`/`SELECT 1; DROP`/`SELECT … INTO`/`FOR UPDATE`/CTE-com-`DELETE`/`SET @x=1`)
  continua barrado com `read="mysql"` pelas **mesmas** `TAGS_PROIBIDAS`. Muda a **lista de funcs**.
- ✅ **As 5 funcs perigosas viram `exp.Anonymous`** com `node.name` = o nome nu (medido):
  `load_file`, `sleep`, `benchmark`, `sys_exec`, `sys_eval` → lista **minúscula** (o validador faz `.lower()`).
- ✅ **`sql_amostra` copia a forma do Postgres** trocando `dialect="mysql"` (medido): `identify=True`
  cita com **crases** (`` `2fa_tokens` ``, `` `Order` ``, `` `schema`.`tab` ``) — mata a injeção e a
  crase é a **assinatura** do dialeto na auditoria. `injetar_limit` é trivial (MySQL tem `LIMIT` nativo).
- 🔴 **O `%s` NÃO parseia no dialeto `mysql`** (medido 2026-07-20, sqlglot 30.12 — ao contrário do
  Postgres): `WHERE x = %s` vira `exp.Mod` e dá `ParseError`. A T9 manteve `validar()`/`injetar_limit()`
  LIGADOS na introspecção porque *"`%s` parseia"* — verdade **só no Postgres**. No MySQL, validar o SQL
  de introspecção (que carrega `%s`) o faz **falhar fechado** → a introspecção quebraria. Corrigido na
  T2 (a rota de introspecção deixa de validar — o identificador já vai por `params`, zero injeção).
- 🔴 **`INTO OUTFILE`/`INTO DUMPFILE` só falham fechado por `ParseError`** (medido — acidente do
  parser, não tag). → **teste de regressão nasce junto** (um upgrade do sqlglot que os parseie abre
  o buraco em silêncio).
- 🔴 **mysql-connector não tem callback por-checkout** (doc): o `pool_reset_session=True` roda
  `RESET CONNECTION` no retorno, que **zera as session vars** → o `SET SESSION TRANSACTION READ ONLY`
  + `max_execution_time` **têm que ser reaplicados a CADA checkout** dentro de um adaptador de pool.
  **Setar uma vez só falha ABERTA.** É o cadeado nº 1 do MySQL, e ele é per-conexão, não do role.
- 🔴 **`schema == database` (§6, medido no código):** 3 das 4 queries de introspecção portam sem
  mudança; **`listar_schemas` com o SQL do Postgres vazaria todos os databases da instância**. O
  default `schema="public"` está cravado na assinatura das tools e não existe no MySQL. A recusa
  `schema != database` precisa de `Settings` (mora no `Nucleo`, não no dialeto stateless).
- 🔴 **A conexão do doctor é psycopg de ponta a ponta** (medido): `ctx.conn.transaction()` não existe
  no mysql-connector, e `checar_allowlist_existe` usa `unnest(%s::text[])` (Postgres puro). E o
  **`CREATE TABLE` do probe faz commit implícito no MySQL** — `ROLLBACK` não desfaz.
- 🔴 **`erros_readonly` (tupla de classes) não encaixa** (doc): 1792/1142 não têm classe própria no
  mysql-connector (só `.errno`). → o contrato vira **predicado** (`erro_readonly(e) -> bool`).

## Decisões desta fase (aprovadas com o Bruno)
1. **Config neutro `db_*`** (decisão do Bruno, 2026-07-20): `pg_host`→`db_host`, `pg_dbname`→`db_dbname`,
   etc. *Breaking change* de custo ~zero (sem PyPI, sem deployment real — só o demo). `db_sslmode`
   fica (semântica Postgres; o MySQL lê as suas próprias chaves de SSL se/quando precisar).
2. **`sql_introspecao` vira membro do `Dialeto`** — o código já tem o precedente (`sql_amostra`,
   `sql_probe_escrita`). Fica atômico com a impl do Postgres.
3. **A introspecção desce pro `Nucleo`** (auditada, como o `amostrar`) — fecha de vez os itens do
   Backlog "recusa na transporte não vira auditoria" e "tools intestáveis". A recusa `schema != database`
   do §6 **precisa** disso: senão ela nasce na tool, fora do `except` que audita — o mesmo bug da T8.
4. **A conexão do doctor vira dialeto-aware AGORA** (não na Fase 2 como o comentário previa — o MySQL
   já quebra `.transaction()`).
5. **Probe de escrita do doctor no MySQL:** como DDL faz commit implícito, usar um probe **DML
   rollback-able** (ex.: `INSERT`/`UPDATE` numa tabela do próprio schema) OU aceitar o resíduo só no
   caso já-ruim (usuário mal-configurado que ACEITA a escrita). Decidir na T7 medindo contra o demo.

---

## Task 1: config neutro `db_*` + extra `mysql`

**Files:** `src/db_mcp/config.py`, `src/db_mcp/dialetos/postgres.py`, `src/db_mcp/doctor.py`,
`pyproject.toml`, `.env.demo`, `.env.example`, `config.example.yaml`, `docker-compose.yml`,
`.github/workflows/ci.yml`, `tests/*` (os que setam `PG_*`), `docs/` e a skill `setup-db-mcp`.

Fundação da fase, **sem** mudança de comportamento — só renomeia a superfície de config.

- [ ] **Step 1:** em `config.py`, renomear os campos `pg_* → db_*` (`db_host`, `db_port`, `db_dbname`,
  `db_user`, `db_password`, `db_sslmode`). **`db_port` sem default universal** (5432≠3306): deixar
  `db_port: int | None = None` e cada `criar_pool` aplicar o default do seu dialeto se `None`. O mypy
  vai apontar **todos** os callers — é a rede.
- [ ] **Step 2:** `pyproject.toml` ganha `[project.optional-dependencies]` com
  `mysql = ["mysql-connector-python>=9"]`. `uv sync --extra mysql` instala.
- [ ] **Step 3:** atualizar `postgres.py::criar_pool` (`s.pg_*` → `s.db_*`, default de porta 5432 se
  `None`), `doctor.py` (o detalhe do `checar_config`, o `make_conninfo` do `checar_auth`, o
  `checar_tcp`), e todo teste que seta `PG_HOST`/etc. → `DB_HOST`/etc.
- [ ] **Step 4:** demo/CI/docs: `.env.demo`, `.env.example`, `config.example.yaml`, `docker-compose.yml`
  (env do container), `ci.yml` (as env vars `PG_*` → `DB_*`), `docs/01-instalacao.md`,
  `docs/02-preparar-o-banco.md`, e a skill `setup-db-mcp`. **Nota:** os arquivos `.env*` são bloqueados
  pra Read — editar via o que não é `.env` e pedir ao Bruno pra ajustar os `.env` na mão se preciso.
- [ ] **Step 5:** `uv run pytest -q` (sem banco) + `--extra`; com o demo Postgres, a suíte inteira +
  `doctor 6/6`. **Zero mudança de expectativa.** Commit: `refactor(config): settings de conexao neutros (db_*) + extra mysql`.

Acréscimo de testes: **0** (renome puro; a suíte prova que nada quebrou).

---

## Task 2: introspecção desce pro `Nucleo` + `sql_introspecao` no dialeto

**Files:** `src/db_mcp/dialetos/base.py`, `src/db_mcp/dialetos/postgres.py`, `src/db_mcp/server.py`,
`tests/test_server.py`, `tests/test_dialetos.py`.

Postgres-only, **comportamento idêntico**. Fecha 2 itens do Backlog e prepara o §6.

- [ ] **Step 1 (contrato):** emendar o `Protocol Dialeto` com a geração de SQL de introspecção — ex.
  `sql_introspecao(tipo: Literal["tabelas","views","colunas","schemas"], **kw) -> tuple[str, tuple]`
  (devolve SQL + params). Implementar em `postgres.py` com o SQL **idêntico** ao que hoje está no
  `server.py` (mesmas queries, mesmos `%s`).
- [ ] **Step 2 (Nucleo):** descer a lógica das tools pro `Nucleo` — ex. `Nucleo.introspectar(tipo, **kw)`
  que resolve o **schema default** (`"public"` no Postgres; será `s.db_dbname` no MySQL — ver T5),
  monta o SQL do dialeto **dentro de um `try/except McpDbError` que AUDITA** (espelhando `amostrar`),
  e chama `consultar`. 🔴 **A rota de introspecção NÃO roda `validar`/`injetar_limit`** (Achado da
  revisão 2026-07-20, medido): o `%s` não parseia no `mysql` e derrubaria toda a introspecção. Concreto:
  `consultar` ganha `validar_sql: bool = True` que porteia **tanto** `validar()` **quanto** `injetar_limit()`;
  a introspecção chama `consultar(..., aplicar_allowlist=False, validar_sql=False)`. **É seguro e
  Postgres-neutro:** o SQL é fixo/interno, o identificador vai por `params` (o `validar` nunca viu o
  valor — só via `%s`), o teto de linhas segue imposto pelo `fetchmany(max_rows)` do `executar` (o
  `LIMIT` era redundante), e o `sql` auditado já era o pré-`injetar_limit`. Rate-limit, teto de bytes e
  auditoria continuam. As tools viram uma linha que delega.
- [ ] **Step 3 (testes):** os testes das tools de introspecção que hoje precisam de banco ganham
  companhia unitária via `Nucleo.introspectar` com `FakeDB` (agora testável sem banco — o item do
  Backlog). Provar que um raise na geração de SQL **audita** (como `test_amostra_com_nome_invalido_e_auditada`).
- [ ] **Step 4:** suíte verde sem/com banco; a fiação e2e (`test_e2e_integration.py`) ainda passa.
  ⚠️ O `sql` **auditado** e as **linhas** continuam idênticos; o que muda é que a introspecção deixa de
  anexar o `LIMIT` redundante (o `fetchmany` já limita) — se algum teste afirmar o SQL executado *com*
  LIMIT na introspecção, ele muda de expectativa e precisa ser ajustado junto. Commit:
  `refactor(server): introspeccao desce pro Nucleo + sql_introspecao no dialeto`.

Acréscimo: **~3-4 testes** (introspecção auditada + testável sem banco).

---

## Task 3: conexão do doctor vira dialeto-aware

**Files:** `src/db_mcp/dialetos/base.py`, `src/db_mcp/dialetos/postgres.py`, `src/db_mcp/doctor.py`,
`tests/test_doctor.py`.

Postgres-only, **doctor 6/6 idêntico**. ✅ **FEITA (2026-07-21, `ba9836e`).**

> 🔧 **Estendida na execução (aprovado pelo Bruno): +2 membros no contrato que o passo a passo
> abaixo esquecia**, e sem os quais a T7 teria que mexer no `doctor.py` de novo — ou seja, a T3 não
> teria preparado nada:
> - **`porta_padrao: int`** (postgres `5432`). O literal `5432` estava cravado em **3 pontos** do
>   `doctor.py` (`checar_config` e `checar_tcp` ×2). Como a T1 tornou `db_port` opcional de propósito
>   (5432≠3306), `db-mcp --dialect mysql doctor` sem `DB_PORT` tentaria TCP na porta do Postgres.
> - **`sql_identidade() -> str`.** O `checar_auth` rodava `SELECT current_user, current_database()`,
>   Postgres puro (⚠️ **documentado, não medido** — sem MySQL vivo até a T7: lá é `database()`).
>   Contrato exige apelidar as colunas `usuario`/`banco`, senão a chave do dict muda com o dialeto.
>
> Bônus: `checar_config` passou a **resolver o dialeto** e a dar erro legível quando ele não tem
> implementação (hoje `mysql`/`sqlserver` são aceitos pelo `Literal` do config) em vez de estourar
> cru na checagem seguinte. Continuam sendo 6 checagens.

- [x] **Step 1 (contrato):** adicionar ao `Dialeto`: `conectar_doctor(s) -> conn` (conexão avulsa,
  autocommit) e `probar_escrita(conn) -> None` (roda o `sql_probe_escrita` e deixa o erro readonly
  subir). Mover o bloco `psycopg.connect(...)`/`make_conninfo` e a dança `transaction()/ROLLBACK`
  do `doctor.py` pro `postgres.py`.
- [x] **Step 2 (doctor):** `Contexto.conn: Any` (era `psycopg.Connection`); `checar_auth` usa
  `dialeto.conectar_doctor(s)`; `checar_somente_leitura` vira `try: dialeto.probar_escrita(ctx.conn)
  except dialeto.<readonly>`; `checar_auth`/`checar_latencia` usam `dialeto.linhas_como_dict(conn)`
  em vez de `conn.execute().fetchone()`. **Reescrever `checar_allowlist_existe` driver-agnóstico:**
  laço Python consultando `information_schema.tables` uma vez por tabela (o `unnest(%s::text[])` é
  Postgres puro).
- [x] **Step 3:** `doctor 6/6` contra o demo Postgres, `write recusado: 25006` idêntico. Commit:
  `refactor(doctor): conexao e probe delegam ao dialeto`.

Acréscimo: ~~**~1-2 testes**~~ → **+5** (dialeto e cursor falsos, sem banco). Os dois caminhos da
allowlist reescrita também foram exercitados **ao vivo** (tabela real e ausente) — o `doctor` normal
cai no atalho `*` e nunca tocaria o laço novo.

---

## Task 4: `erros_readonly` vira predicado

**Files:** `src/db_mcp/dialetos/base.py`, `src/db_mcp/dialetos/postgres.py`, `src/db_mcp/doctor.py`.

O campo `erros_readonly: tuple[type[Exception], ...]` não encaixa no MySQL (1792/1142 sem classe
própria). Vira **`erro_readonly(e: Exception) -> bool`** (predicado): Postgres testa `isinstance`
das duas classes; MySQL testará `e.errno in {1792, 1142}` (T5). O doctor troca
`except dialeto.erros_readonly` por captura ampla + `if dialeto.erro_readonly(e)`.

- [x] Postgres-only, comportamento idêntico. Commit: `refactor(dialeto): erro_readonly como predicado`.
  ✅ **FEITA (2026-07-21, `9ba6166`).**

Acréscimo: ~~**0**~~ → **+1**. O doctor vivo prova o caminho feliz, mas não o perigoso: um erro de
banco que **não** é recusa de escrita não pode virar "somente-leitura confirmado". Como o `except`
agora é largo, essa é a regressão que guarda o cadeado que falha aberta.

> **Nota de sequência:** T2-T4 são o "prepara o contrato no Postgres, sem mudar comportamento" — o
> mesmo padrão que a Fase 0 usou (refatora primeiro, adiciona o dialeto depois). Podem virar 1 ou 3
> commits; o que **não** pode é a mudança de `Protocol` sem a impl do Postgres junto.

---

## Task 5: `dialetos/mysql.py` — o dialeto

**Files:** `src/db_mcp/dialetos/mysql.py` (novo), `src/db_mcp/dialetos/__init__.py`, `tests/test_dialetos.py`.

O coração da fase. `DialetoMySQL` implementa **todo** o contrato (agora ampliado por T2-T4).

- [ ] **Step 1:** `nome="mysql"`, `sqlglot_dialeto="mysql"`,
  `funcs_proibidas=frozenset({"load_file","sleep","benchmark","sys_exec","sys_eval"})` (minúsculas).
  ⚠️ **A lista é escolhida, não medida-completa** (revisão 2026-07-20): medido que `get_lock` (função
  **padrão**, vetor de lock/DoS) também vira `exp.Anonymous` e passaria; já `sys_exec`/`sys_eval` são
  UDFs **não-padrão** (`lib_mysqludf_sys`, quase nunca presentes). Reavaliar contra o spec §5.4 —
  incluir `get_lock`/`release_lock`/`sleep`-family se o spec concordar. (Defesa em profundidade: o limite
  real é o `GRANT SELECT`, mas a blocklist não deveria omitir uma função padrão barrável.)
  `schema_padrao` — ⚠️ **não é estático:** no MySQL o "schema padrão" é o **database configurado**.
  Resolver no `Nucleo` (T2) lendo `s.db_dbname`, ou expor `schema_padrao_de(s)` no dialeto. Decidir
  medindo o que fica mais limpo.
- [ ] **Step 2 (pool adapter):** `criar_pool(s)` devolve uma **classe adaptadora** (o `PoolLike` do
  contrato exige `.connection()` context manager; o `MySQLConnectionPool` cru só tem
  `get_connection()`/`close()`). 🔬 **Antes de codar o adaptador, MEDIR:** `uv sync --extra mysql` e
  confirmar empiricamente que `pool_reset_session=True` de fato zera o `SET SESSION TRANSACTION READ ONLY`
  no retorno ao pool — a base do design "reaplica por-checkout" está em **(doc)**, não medida, e é o
  único cadeado que *falha aberta*. Se o reset não limpar a var, o design simplifica; se limpar, a
  reaplicação é obrigatória. O adaptador:
  - cria `pooling.MySQLConnectionPool(pool_name=..., pool_size=min(s.pool_max, 32),
    pool_reset_session=True, host=s.db_host, port=s.db_port or 3306, user=..., password=...,
    database=s.db_dbname, autocommit=True)`;
  - `.connection()` = `@contextmanager` que faz `get_connection()`, **reaplica a CADA checkout**
    `SET SESSION TRANSACTION READ ONLY` + `SET SESSION max_execution_time = <s.statement_timeout_ms>`
    (🔴 senão falha ABERTA — o `RESET CONNECTION` do retorno zerou), `yield` a conn, e `cnx.close()`
    (devolve ao pool);
  - import **lazy** de `mysql.connector` dentro dos métodos (o extra é opcional).
- [ ] **Step 3:** `linhas_como_dict(conn)` = `@contextmanager` com `conn.cursor(dictionary=True)` +
  `try/finally: cur.close()`. `erro_do_banco(e)=isinstance(e, mysql.connector.Error)`;
  `erro_de_timeout(e)= … and getattr(e,"errno",None)==3024`; `erro_readonly(e)= …errno in {1792,1142}`.
- [ ] **Step 4:** `sql_amostra` = a forma do Postgres com `dialect="mysql"` (crases). `sql_probe_escrita`
  = ver T7 (DML rollback-able vs DDL). `sql_introspecao` — as 3 queries que portam + **`listar_schemas`
  devolvendo SÓ `s.db_dbname`** (nunca `information_schema.schemata` da instância — §6). `conectar_doctor`
  = `mysql.connector.connect(autocommit=True, …)`. `probar_escrita` = cursor + probe + `rollback()`.
- [ ] **Step 5:** registrar no `_REGISTRO` (`dialetos/__init__.py`) — **uma linha**:
  `"mysql": _mysql`. O `test_invariante_todo_dialeto` **já existente** passa a rodar contra o MySQL
  (round-trip do `sqlglot_dialeto="mysql"` ✅ e `funcs_proibidas` não-vazia ✅) — o gate de CI cobre
  o dialeto novo de graça.
- [ ] **Step 6:** commit `feat(dialeto): mysql`.

Acréscimo: os testes do invariante passam a incluir o mysql (parametrizado) — **+N automático**.

---

## Task 6: corpus de ataque MySQL + regressão `INTO OUTFILE`

**Files:** `tests/test_sql.py`, `tests/test_ataques_e2e.py`.

- [ ] **Step 1:** em `test_sql.py`, ao lado de `PG = obter_dialeto("postgres")`, criar
  `MY = obter_dialeto("mysql")` + `_validar_my`, e a **tabela de ataques MySQL**: as 5 funcs
  (`load_file`/`sleep`/`benchmark`/`sys_exec`/`sys_eval`) barradas por `SomenteLeitura`, o corpus
  genérico (UPDATE/CREATE/multi-stmt/INTO/FOR UPDATE/CTE-DELETE) barrado, e **`INTO OUTFILE`/`DUMPFILE`
  recusados** (verificar **recusa** — qualquer `McpDbError` —, não presumir que segue `ParseError`;
  se o sqlglot mudar, o teste avisa).
- [ ] **Step 2:** `test_ataques_e2e.py` parametrizado por dialeto (a estrutura já prevê isso): um
  subconjunto representativo contra o MySQL vivo (a assinatura de fiação é a **crase** no SQL auditado).
- [ ] Commit: `test: corpus de ataque mysql + regressao INTO OUTFILE`.

Acréscimo: **~15-20 testes** (o corpus MySQL + regressão + e2e).

---

## Task 7: demo MySQL (docker-compose profile + seed)

**Files:** `docker-compose.yml`, `demo/init-mysql/01-schema.sql`, `02-seed.sql`, `03-mcp-ro.sql` (novos).

- [ ] **Step 1:** serviço `mysql` sob `profiles: ["mysql"]` (`image: mysql:8`,
  `container_name: db-mcp-demo-mysql`, `MYSQL_DATABASE=demo` + `MYSQL_ROOT_PASSWORD`, porta
  **`3307:3306`** — 3307 no host pra não colidir com MySQL local, espelhando o 5433 do Postgres,
  volume `./demo/init-mysql:/docker-entrypoint-initdb.d:ro`, healthcheck `mysqladmin ping`). O serviço
  `db` (Postgres) fica **sem profile** → `docker compose up -d` segue = só Postgres (compat com o
  CLAUDE.md); `docker compose --profile mysql up -d` sobe os dois.
- [ ] **Step 2:** seed traduzido: `id INT AUTO_INCREMENT PRIMARY KEY`; `text→VARCHAR/TEXT`;
  `numeric(10,2)→DECIMAL(10,2)`; `boolean→TINYINT(1)`; `date DEFAULT CURRENT_DATE→DATE DEFAULT (CURDATE())`.
  Usuário: `CREATE USER 'mcp_ro'@'%' … ; GRANT SELECT ON demo.* TO 'mcp_ro'@'%';` — ⚠️ **sem**
  `default_transaction_read_only` (não existe no MySQL): o read-only do usuário de demo é só o
  `GRANT SELECT` (o "suspensório"); o "cinto" (`SET SESSION TRANSACTION READ ONLY`) é per-conexão,
  aplicado pelo pool da app (T5).
- [ ] **Step 3 — decidir o probe do doctor (medindo):** `sql_probe_escrita` do MySQL. Se DDL
  (`CREATE TABLE`) → o usuário read-only recusa com 1142 antes de criar (inócuo), MAS um usuário
  ruim que aceitar deixa a tabela (commit implícito). Preferir um probe **DML rollback-able** contra
  o schema (ex. `UPDATE` numa tabela do demo com `WHERE 1=0`, ou `INSERT` revertível) que o
  `GRANT SELECT` recusa com 1142/1792 e que, se aceito, o `rollback()` desfaz. Medir contra o demo.
  ⚠️ **Coerência autocommit×rollback (revisão 2026-07-20):** a T5 step 4 põe `conectar_doctor` com
  `autocommit=True`, onde `rollback()` é **no-op** e um DML aceito **commita na hora** — não dá pra ter
  as duas coisas (autocommit **e** probe rollback-able). Resolver escolhendo UM: (a) probe
  `UPDATE … WHERE 1=0` — zero linhas afetadas ⇒ zero resíduo mesmo se aceito, e o rollback vira
  irrelevante (preferido); ou (b) conn do probe **não**-autocommit, com `rollback()` de verdade.
- [ ] **Step 4:** `docker compose --profile mysql up -d` + `db-mcp --dialect mysql doctor` → **6/6**.
  Commit: `feat(demo): container mysql com profile + seed read-only`.

> ⚠️ **O `--dialect` não alcança o subcomando `doctor`** (gotcha do CLAUDE.md, marcador `# FASE 1:`
> no `cli.py`): nesta fase a flag passa a **mentir em silêncio** se o `doctor` carregar o `Settings`
> sozinho com default `postgres`. **Corrigir o roteamento do `--dialect` até o `doctor` é parte desta
> task** — senão `db-mcp --dialect mysql doctor` roda contra o dialeto errado.

---

## Task 8: CI — job de integração MySQL

**Files:** `.github/workflows/ci.yml`.

- [ ] Replicar o job de integração pro `mysql:8` (service container, `MYSQL_DATABASE=demo` +
  `MYSQL_ROOT_PASSWORD`, `--health-cmd "mysqladmin ping"`), semeando num **step** com o cliente
  (`apt-get install default-mysql-client`; laço `mysql … demo < demo/init-mysql/NN.sql`) — os service
  containers **não** montam arquivos do repo (o checkout vem depois), então é step, não volume. Rodar
  a suíte com as env vars `DB_*` de MySQL. Commit: `ci: job de integracao mysql`.

---

## Task 9: docs — a tabela honesta dos cadeados por dialeto

**Files:** `README.md`, `docs/02-preparar-o-banco.md`, `docs/VISAO-GERAL.md`, `docs/00-para-leigos.md`,
`docs/03-arquitetura.md`, `CHANGELOG.md`.

Agora o MySQL **existe** — a tabela do §4 vira verdade e **deve** entrar (documentar capacidade que
existe é o oposto do que a Fase 0 evitou).

- [ ] **Step 1:** README + `02-preparar-o-banco.md` ganham a **tabela dos 3 cadeados por dialeto**
  (§4 do spec). A frase "o próprio Postgres recusa a escrita" vira **por-dialeto**: no MySQL o cinto
  é `SET SESSION TRANSACTION READ ONLY` (per-conexão, mais fraco), o suspensório é o `GRANT`. A nota
  de estado atual do README passa a "PostgreSQL e MySQL prontos; SQL Server na Fase 2".
- [ ] **Step 2:** `VISAO-GERAL.md`/`00-para-leigos.md` — o enquadramento deixa de ser só-Postgres.
  `03-arquitetura.md` — a tabela de componentes ganha `dialetos/mysql.py`. `CHANGELOG.md` — entry
  `0.4.0` (dialeto MySQL). Commit: `docs: cadeados por dialeto + MySQL no estado atual`.

---

## Task 10: verificação final da fase

- [ ] `docker compose down -v && docker compose --profile mysql up -d` (Postgres **e** MySQL frescos).
- [ ] `uv sync --extra mysql` · `ruff check` · `ruff format --check` · `mypy src` limpos.
- [ ] `uv run pytest -q` (sem banco: integração pulada) · com **ambos** os bancos:
  `DB_*` de Postgres → suíte verde; `DB_*` de MySQL → suíte verde. **Zero skipped** com banco.
- [ ] `db-mcp --dialect postgres doctor` **6/6** · `db-mcp --dialect mysql doctor` **6/6**.
- [ ] `test_invariante_todo_dialeto` verde para `postgres` **e** `mysql`.
- [ ] Commit final + `/fechar` (sync do CLAUDE.md: Fase 1 fechada, próxima = Fase 2 SQL Server).

**Se qualquer `doctor` não fechar 6/6, ou a suíte não estiver verde nos dois bancos, a fase não terminou.**

---

## Definição de pronto da Fase 1
- [ ] `db-mcp --dialect {postgres,mysql} doctor` fecha **6/6** contra os dois containers de demo.
- [ ] Suíte completa verde com **cada** banco (zero skipped) e sem banco (integração pulada).
- [ ] `ruff check`, `ruff format --check`, `mypy src` limpos.
- [ ] O corpus de ataque roda e barra tudo **nos dois** dialetos; `INTO OUTFILE`/`DUMPFILE` têm
  teste de regressão.
- [ ] `test_invariante_todo_dialeto` cobre o `mysql`.
- [ ] **Zero mudança de comportamento no Postgres** — os testes do Postgres não mudaram de expectativa.
- [ ] O read-only do MySQL é reaplicado **a cada checkout** do pool (não uma vez só) — provado por
  teste ou verificação e2e (senão falha aberta).
- [ ] `dialetos/base.py` não importa driver nenhum.
- [ ] README diz a verdade do §4 — a força de cada cadeado por dialeto, sem promessa uniforme.

## Riscos / gotchas herdados (do CLAUDE.md e do grounding)
- 🔴 **read-only per-checkout** (mysql-connector sem callback) — o maior. Setar uma vez falha aberta.
- 🔴 **`schema==database`** — `listar_schemas` do Postgres vazaria a instância; a recusa `schema!=db`
  precisa nascer **auditada** (no Nucleo), senão é o bug da T8 de novo.
- 🔴 **DDL faz commit implícito no MySQL** — o probe do doctor precisa ser rollback-able ou aceitar
  resíduo no caso já-ruim.
- 🟡 **`INTO OUTFILE` só barrado por `ParseError`** — regressão trava o contrato.
- 🟡 **`--dialect` não alcança o `doctor`** — corrigir nesta fase (a flag mentiria).
- 🟡 **`erros_readonly` tupla→predicado** — casar por classe base no MySQL daria falso "read-only ok".
- 🟡 **pool_size teto 32** no mysql-connector — clampar `pool_max`.
