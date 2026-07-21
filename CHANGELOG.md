# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e o projeto segue [Versionamento Semântico](https://semver.org/lang/pt-BR/).

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
