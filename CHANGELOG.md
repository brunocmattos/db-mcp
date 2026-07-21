# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e o projeto segue [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [0.5.0] - 2026-07-21

Fase 2: **o SQL Server passa a funcionar**. `db-mcp --dialect sqlserver doctor` fecha 6/6
contra um SQL Server 2022 real, a suíte roda verde nos três bancos, e o CI ganha um oitavo
job (`integration-sqlserver`). Diferente das duas fases anteriores, esta **tocou o
núcleo**: o SQL Server expôs um bug real em `guardrails/policy.py` e duas suposições erradas
em `doctor.py` — nenhuma das três hipotética, todas só apareceram rodando contra o banco de
verdade pela primeira vez.

### Added
- **Dialeto SQL Server** (`dialetos/sqlserver.py`): conexão **sem pool**. O pymssql não tem
  pool nem `RESET CONNECTION`, e o próprio SQL Server não tem nenhum reset de sessão
  (`DISCARD ALL`/`RESET CONNECTION`) para reimplementar por conta própria — em vez disso, o
  dialeto abre uma conexão nova a cada consulta: a conexão nova É o reset, e o gap que fez o
  MySQL falhar aberto na Fase 1 (`pool_reset_session` zerando o read-only) deixa de existir
  em vez de virar resíduo. Custo medido do handshake: ~14,3 ms (15,61 ms conexão nova vs
  1,28 ms reusada), cerca de 1% do round-trip percebido numa consulta via MCP.
- **`erro_readonly` reconhece `262`** (CREATE TABLE permission denied) como confirmação de
  somente-leitura, e **recusa `229` de propósito**: esse código também sobe por falta de
  `SELECT` simples, não só por escrita negada — casá-lo faria o doctor confirmar
  "somente-leitura" numa conexão que na verdade falhou por outro motivo, no único banco
  onde o `GRANT` é o cadeado inteiro.
- **Lista de funções perigosas do T-SQL** (`FUNCS_PROIBIDAS_SQLSERVER`): `openquery`,
  `opendatasource`, `openrowset` (o vetor de loopback mais grave do SQL Server), os `xp_*`
  como `xp_cmdshell` (sobra-defesa: são stored procedures estendidas, só invocáveis via
  `EXEC`, nunca dentro de um `SELECT` — a forma de ataque real já morre antes da blocklist)
  e as `fn_*` de auditoria/trace/log de transação (`fn_get_audit_file`,
  `fn_trace_gettable`, `fn_dblog`, `fn_dump_dblog`, `fn_my_permissions`).
- **Corpus de ataque** (`tests/test_sql_sqlserver.py`) com a mesma distinção de dois grupos
  que a Fase 1 estabeleceu para o MySQL: o que a blocklist de fato barra (o `openrowset` na
  forma padrão de 3 argumentos, os `xp_*` e `fn_*` acima) e o que hoje só falha fechado
  **por acidente de parser** (`OPENROWSET` com credencial via `;` ou `BULK`,
  `WAITFOR DELAY`, `EXECUTE AS LOGIN`, o separador de lote `GO`) — regressão deliberada,
  para que um upgrade do sqlglot que passe a parsear essas formas não abra o buraco em
  silêncio.
- **Demo SQL Server**: `docker compose --profile sqlserver up -d` sobe um SQL Server 2022
  na porta 1434 com `.env.demo-sqlserver` pronto e a receita de usuário `mcp_ro` já com os
  `DENY` necessários (`demo/init-sqlserver/03-mcp-ro.sql`).
- **CI**: job `integration-sqlserver` — o seed roda via `docker exec`/`sqlcmd`, porque a
  imagem do SQL Server, diferente das do Postgres/MySQL, não aplica `.sql` de um diretório
  de init sozinha — e o extra `sqlserver` (`pymssql>=2.3`) somado ao `--all-extras` do CI.
- **Documentação honesta dos cadeados por dialeto** (README, `02-preparar-o-banco.md`,
  `CLAUDE.md`): a tabela ganha a coluna do SQL Server — não existe read-only de sessão
  (`SET TRANSACTION READ ONLY` → erro 156, sintaxe inválida) nem reset de sessão; o
  `GRANT`/`DENY` é o único cadeado que sobra. Receita nova em `02-preparar-o-banco.md` para
  o vazamento de metadado medido no SQL Server: sem os `DENY`, um login com `GRANT SELECT`
  numa tabela ainda enxerga todos os bancos da instância e todos os logins SQL.

### Fixed
- **`injetar_limit` reemitia o SQL de entrada em vez de reemitir no dialeto alvo**, nos
  dois atalhos que existiam para pular a formatação quando o `LIMIT`/`FETCH` já estava
  dentro do teto. O sqlglot faz parse leniente de `LIMIT` mesmo lendo como `tsql` — sintaxe
  que o T-SQL não tem —, então uma consulta com `LIMIT` e valor dentro do teto batia nesse
  atalho e saía **intocada**; o pymssql recusava com "Incorrect syntax near '1'", porque
  `LIMIT` não existe no SQL Server. Bug real, não hipotético: só apareceu rodando o corpus
  e2e contra um SQL Server de verdade pela primeira vez. Fix: os dois atalhos passam a
  devolver `arvore.sql(dialect=dialeto)` em vez do `sql` de entrada; Postgres e MySQL saem
  idênticos (medido, mesmo texto), só o T-SQL muda (`LIMIT` vira `TOP`).
- **`doctor.py` tinha duas suposições implícitas de Postgres/MySQL.** `checar_latencia`
  rodava `SELECT 1` cru — o cursor `as_dict` do pymssql levanta erro numa coluna sem nome;
  virou `SELECT 1 AS um`, SQL genérico, sem o núcleo passar a conhecer o driver.
  `checar_somente_leitura` só lia `getattr(e, "sqlstate", "")` — o pymssql não expõe esse
  atributo, e a mensagem da checagem virava só "OperationalError", perdendo o número que
  identifica a recusa; o fix cai para o primeiro item de `.args` (onde o pymssql põe o
  número, ex. `262`) só quando `sqlstate` não existir.
- **`allowlist` descartava o `catalog` de uma referência de tabela** (`tabelas_referenciadas`
  montava o nome só com `t.db + t.name`), então `outrodb.public.clientes` virava
  `public.clientes` e casava com a entrada feita para o banco corrente. Latente e não
  explorável no Postgres/MySQL (ambos recusam nome de 3 partes no próprio servidor), mas o
  SQL Server **executa** esse nome — a Fase 2 abriria o buraco no dia em que existisse. Por
  isso o fix veio antes do plano da fase, sozinho: qualquer referência que nomeie um
  catalog passa a ser **recusada**, mesmo com `allowlist=["*"]`.

### Changed
- `pyproject.toml` ganha o extra `sqlserver` (`pymssql>=2.3` — sem pool nem reset de
  sessão, medido: nenhum símbolo "pool" no módulo).

## [0.4.0] - 2026-07-21

Fase 1: **o MySQL passa a funcionar**. `db-mcp --dialect mysql doctor` fecha 6/6, e a
suíte roda verde contra os dois bancos. O núcleo não mudou — entrou um módulo de
dialeto e uma linha no registro, que era exatamente a aposta da Fase 0.

### Added
- **Dialeto MySQL** (`dialetos/mysql.py`): pool `mysql-connector` com
  `pool_reset_session`, cursor-dict, tradução de erro do driver, introspecção,
  probe de escrita do doctor e a sua própria lista de funções perigosas
  (`load_file`, `sleep`, `benchmark`, os locks nomeados `get_lock`/`release_lock`/…,
  `sys_exec`/`sys_eval`). Driver como extra opcional: `uv sync --extra mysql`.
- **Demo MySQL**: `docker compose --profile mysql up -d` sobe um MySQL 8.4 semeado
  na porta 3307, espelhando o demo do Postgres, com `.env.demo-mysql` pronto.
- **CI**: job `integration-mysql` (service MySQL, seed, suíte completa e `doctor`),
  e `--all-extras` nos syncs — sem o driver, o mypy não resolvia o import e o gate
  de invariante do dialeto se pulava em silêncio.
- **Corpus de ataque MySQL** (`tests/test_sql_mysql.py`), com regressão deliberada
  para `INTO OUTFILE`/`DUMPFILE` — hoje eles falham fechado por `ParseError`, o que é
  acidente e não desenho; o teste exige **recusa**, não um mecanismo, para que um
  upgrade do sqlglot não abra o buraco em silêncio.
- **Documentação honesta dos cadeados por dialeto** (README, `02-preparar-o-banco.md`,
  `00-para-leigos.md`): o cadeado nº 1 é **mais fraco no MySQL**, onde não existe
  equivalente ao `default_transaction_read_only` por usuário. Lá o `GRANT SELECT`
  restrito é a proteção principal, não um extra.

### Fixed
- **`--dialect` não alcançava o subcomando `doctor`** (o doctor carrega o `Settings`
  sozinho). Enquanto só o Postgres existia era inofensivo; com o MySQL registrado, a
  flag passaria a **mentir em silêncio**, rodando as 6 checagens contra o outro dialeto.
- **Tools de introspecção defaultavam `schema="public"`**, um valor que só existe no
  Postgres — no MySQL toda chamada sem argumento seria recusada. O default virou
  `None`: quem sabe o schema padrão é o dialeto (no MySQL, o database configurado).
- **`doctor` com a porta 5432 cravada** em três pontos, apesar de `db_port` ser
  opcional desde a Fase 1 T1. A porta padrão passou a vir do dialeto.

### Changed
- O `doctor` deixou de importar `psycopg`: conexão, probe de escrita, porta padrão e
  SQL de identidade saem do contrato `Dialeto`. `erros_readonly` (tupla de classes)
  virou o predicado `erro_readonly(e)` — o mysql-connector não dá classe própria aos
  erros 1792/1142, e casar por classe base daria falso "read-only confirmado".

## [0.3.0] - 2026-07-20

Fase 0 do design multi-dialeto: o núcleo deixa de conhecer PostgreSQL. Nenhuma
mudança de comportamento — a suíte existente é a rede de segurança.

### Changed
- **BREAKING**: `pg-readonly-mcp` passa a se chamar `db-mcp` (pacote `db_mcp`,
  comando `db-mcp`). Quem tinha o MCP registrado no cliente precisa reapontar.
- Arquitetura multi-dialeto: o contrato `Dialeto` (`dialetos/base.py`, sem driver)
  isola o que muda entre bancos — pool, cursor-dict, tradução de exceção do driver,
  lista de funções perigosas e o probe de escrita do `doctor`. Nesta versão só o
  dialeto `postgres` existe; MySQL e SQL Server vêm nas fases 1 e 2. O `db.py` virou
  fachada fina e não importa mais `psycopg`.

### Fixed
- `injetar_limit` emitia sempre em sintaxe PostgreSQL. Sem efeito no dialeto
  `postgres`; teria quebrado o SQL Server (onde `LIMIT` vira `TOP`).
- `amostra` montava `LIMIT` na mão e escapava da transpilação; passa a vir do dialeto.
- Introspecção passa a usar query parameters em vez de interpolar o nome de
  schema/tabela num literal de string protegido só por regex.
- Recusa por SQL malformado (aspa não fechada → `TokenError`) escapava do validador
  sem virar auditoria; o `except` passou a cobrir a família `SqlglotError` inteira.

## [0.2.0] - 2026-07-10

Primeira versão pública. Servidor MCP somente-leitura para qualquer PostgreSQL.

### Recursos

- **Seis ferramentas MCP:** introspecção de schemas, tabelas e views, `descrever_tabela`,
  `amostra` e `consultar` (um `SELECT` livre, validado — desligável com `ALLOW_FREEFORM_SQL=false`).
- **Três camadas de defesa:** usuário read-only no banco (`GRANT SELECT` +
  `default_transaction_read_only`), `pg_hba` por IP, e o validador de aplicação — só `SELECT`,
  instrução única, sem funções perigosas, com allowlist de tabelas, `LIMIT` automático, tetos de
  linhas e bytes, rate limit e, no transporte HTTP, autenticação Bearer com _fail-closed_.
- **Transportes stdio e HTTP.** O modo HTTP exige `AUTH_TOKEN` e recusa subir sem ele.
- **Comando `doctor`** com seis checagens de preflight (config, TCP, autenticação, read-only,
  allowlist e latência).
- **Trilha de auditoria:** uma linha por consulta, incluindo as recusadas.
- **Instalação assistida:** `SETUP.md` e uma skill do Claude Code que pergunta os parâmetros,
  ajuda a criar o usuário read-only, preenche a config e registra o MCP no cliente.
- **Demonstração em Docker:** um Postgres semeado com o usuário read-only pronto, para
  experimentar em 30 segundos sem um banco próprio.
