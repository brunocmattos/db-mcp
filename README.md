# db-mcp

[![CI](https://github.com/brunocmattos/db-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/brunocmattos/db-mcp/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://img.shields.io/badge/mypy-strict-blue)](https://mypy-lang.org/)

Servidor MCP somente-leitura para bancos SQL. Dá a agentes de IA (Claude Desktop,
Claude Code, automações) acesso de introspecção e `SELECT` a tabelas e views, sem
escrever, alterar schema ou derrubar o banco.

O código não conhece nenhum banco específico: você aponta o MCP pro seu banco
preenchendo a config. Nenhum host, senha ou nome de tabela real fica no repositório.

> **Estado atual:** **PostgreSQL** e **MySQL** prontos. SQL Server vem na fase 2 do
> design multi-dialeto — o código já está estruturado pra recebê-lo, mas ainda não o
> suporta. Escolha o banco com `DIALETO=postgres|mysql` ou `--dialect`.
> O driver do MySQL é um extra opcional: `uv sync --extra mysql`.

## Os três cadeados

Defesa em profundidade, três camadas independentes — se uma falha, a próxima ainda segura.
As duas primeiras são configuração de infra; a terceira é o código deste repo.

1. **No banco:** um usuário dedicado que só pode ler.
2. **Na rede:** o servidor só aceita esse usuário vindo das faixas de IP conhecidas
   (`pg_hba.conf` no Postgres; host do usuário / firewall no MySQL).
3. **Na aplicação:** o validador SQL (`sqlglot`: só `SELECT`, uma instrução, sem funções
   perigosas), allowlist de tabelas, `LIMIT` automático, teto de linhas/bytes, rate limit
   e, no transporte HTTP, autenticação por token Bearer.

### O cadeado nº 1 não tem a mesma força em todo banco

Esta é a parte que a maioria das ferramentas não conta. O cadeado do banco é o mais
importante — é o único que **não depende do nosso código** — e ele é genuinamente mais
fraco no MySQL do que no PostgreSQL:

| | PostgreSQL | MySQL |
|---|---|---|
| **Permissão** ("suspensório") | `GRANT SELECT` | `GRANT SELECT` |
| **Transação read-only** ("cinto") | `default_transaction_read_only = on` **no próprio usuário** | `SET SESSION TRANSACTION READ ONLY`, **por conexão** |
| Quem garante o cinto | o **servidor**, em toda conexão daquele usuário | a **aplicação**, a cada conexão que pega do pool |
| Reset de sessão entre usos | `DISCARD ALL` | `RESET CONNECTION` |
| **Força real** | cinto **e** suspensório | suspensório forte + cinto que depende do app |

**O que isso significa na prática:** no PostgreSQL, mesmo que este programa tenha um bug,
o banco recusa a escrita — o `default_transaction_read_only` está gravado no usuário.
No MySQL **não existe equivalente por usuário**: o `SET SESSION TRANSACTION READ ONLY`
vale só para a conexão atual, e nós [o reaplicamos a cada
checkout](src/db_mcp/dialetos/mysql.py) do pool (medido: o reset do pool zera a
configuração, então aplicá-la uma vez falharia **aberto**).

👉 **Por isso, no MySQL, o `GRANT SELECT` não é opcional — é o que realmente segura.**
Conceda apenas `SELECT`, apenas nas tabelas que a IA deve ver. Vale para os dois bancos,
mas no MySQL é a diferença entre ter e não ter proteção.

## Ferramentas expostas

| Ferramenta | O que faz |
|---|---|
| `listar_schemas()` | schemas visíveis |
| `listar_tabelas(schema)` | tabelas de um schema |
| `listar_views(schema)` | views de um schema |
| `descrever_tabela(tabela, schema)` | colunas e tipos |
| `amostra(tabela, n)` | primeiras N linhas (passa pela allowlist) |
| `consultar(sql)` | um `SELECT` validado (desligável com `ALLOW_FREEFORM_SQL=false`) |

A introspecção lista metadados livremente; a allowlist só entra nas ferramentas que leem
linhas de dados (`amostra`, `consultar`).

## Experimente em 30 segundos

Não precisa de um banco seu. O `docker-compose.yml` sobe um já semeado e com o
usuário read-only `mcp_ro` pronto:

```bash
docker compose up -d                     # Postgres de demo na porta 5433
uv sync                                  # instala o MCP
uv run db-mcp --env .env.demo doctor     # confere tudo
```

Saída (real, contra o container acima):

```text
== db-mcp doctor ==
✅ [OK] Config OK  —  mcp_ro@localhost:5433/demo · dialeto=postgres · allowlist=['*']
✅ [OK] TCP OK  —  conectou em 8 ms
✅ [OK] Autenticou  —  current_user=mcp_ro · db=demo
✅ [OK] Somente-leitura confirmado  —  write recusado: 25006 ReadOnlySqlTransaction
✅ [OK] Allowlist = todas (*)  —  nada específico a verificar
✅ [OK] Latência SELECT 1  —  mediana 0.4 ms (min 0.4 · max 0.6)

6 ok · 0 falha(s) · 0 pulada(s)
```

Para o MySQL é o mesmo roteiro, atrás de um profile do compose:

```bash
docker compose --profile mysql up -d          # MySQL de demo na porta 3307
uv sync --extra mysql                         # instala o MCP + o driver do MySQL
uv run db-mcp --env .env.demo-mysql doctor
```

```text
== db-mcp doctor ==
✅ [OK] Config OK  —  mcp_ro@127.0.0.1:3307/demo · dialeto=mysql · allowlist=['*']
✅ [OK] TCP OK  —  conectou em 1 ms
✅ [OK] Autenticou  —  current_user=mcp_ro@% · db=demo
✅ [OK] Somente-leitura confirmado  —  write recusado: 42000 ProgrammingError
✅ [OK] Allowlist = todas (*)  —  nada específico a verificar
✅ [OK] Latência SELECT 1  —  mediana 0.6 ms (min 0.5 · max 0.7)

6 ok · 0 falha(s) · 0 pulada(s)
```

Repare no quarto check, e na diferença entre os dois: no Postgres a escrita é recusada
com `25006` (a transação é read-only — o *cinto*, que vem do próprio usuário do banco);
no MySQL, com `42000`/`1142` (o usuário não tem o privilégio — o *suspensório*). É a
tabela acima aparecendo na prática.

Uma consulta
passa pelo validador e volta com dados; uma escrita é barrada antes de chegar lá:

```
consultar("SELECT nome, cidade FROM clientes ORDER BY id LIMIT 3")
→ {"linhas": [{"nome": "Ana Souza",  "cidade": "Porto Alegre"},
              {"nome": "Bruno Lima", "cidade": "Curitiba"},
              {"nome": "Carla Nunes","cidade": "São Paulo"}],
   "truncado": false, "total": 3}

consultar("UPDATE clientes SET cidade = 'x'")
→ {"erro": "somente_leitura", "detalhe": "apenas comandos SELECT são permitidos"}
```

Para subir o servidor apontado num deles: `uv run db-mcp --env .env.demo`
(ou `--env .env.demo-mysql`). Para desligar e apagar tudo:
`docker compose --profile mysql down -v`.

## Instalação

Requer Python 3.11+ e o gerenciador [`uv`](https://docs.astral.sh/uv/) (testado com 3.12
e 3.13). O pacote não está publicado no PyPI: instala-se clonando o repo e rodando `uv sync`.

Passo a passo na mão em [`docs/01-instalacao.md`](docs/01-instalacao.md). Para deixar o
Claude conduzir, abra esta pasta no Claude Code e siga [`SETUP.md`](SETUP.md): uma skill
pergunta os parâmetros do seu banco, ajuda a criar o usuário read-only, preenche a config,
roda a verificação e registra o MCP no cliente.

Resumo (na mão):

```bash
uv sync                   # instala tudo (Postgres)
uv sync --extra mysql     # ...ou com o driver do MySQL junto
cp .env.example .env      # preencha DIALETO/DB_HOST/DB_DBNAME/DB_PASSWORD...
uv run db-mcp doctor      # config, rede, auth, read-only, allowlist, latencia
uv run db-mcp             # sobe o servidor (stdio)
```

O `doctor` só fica verde com o banco já preparado (usuário `mcp_ro` com `GRANT SELECT`
+ liberação de rede, ver [`docs/02-preparar-o-banco.md`](docs/02-preparar-o-banco.md)).
Sem esse passo, as checagens de auth e de read-only falham — de propósito.

## Verificação

`uv run db-mcp doctor` roda 6 checagens (config válida, TCP alcança o host,
autentica como o usuário read-only, confirma que é read-only, tabelas da allowlist existem,
latência de uma query trivial) e sai com código `0` se tudo passar. Veja
[`docs/04-troubleshooting.md`](docs/04-troubleshooting.md) para interpretar cada falha.

## Configuração

Segredos em `.env`; ajustes em `config.yaml`. Copie de `.env.example` e `config.example.yaml`
(só placeholders). A lista completa de parâmetros está em [`docs/DESIGN.md`](docs/DESIGN.md) (§6).

O transporte padrão é stdio, que não usa autenticação. Para expor por HTTP
(`TRANSPORT=http`), o servidor exige `AUTH_TOKEN` e recusa subir sem ele; o token é
validado como Bearer em toda requisição.

## Documentação

- [`docs/00-para-leigos.md`](docs/00-para-leigos.md): explicação do zero para quem **não é da área** — o que é um MCP, o que é este, como usar, quais as seguranças, como criar um MCP do zero e como adaptar para outros bancos.
- [`docs/VISAO-GERAL.md`](docs/VISAO-GERAL.md): o projeto explicado do começo ao fim — o que é, por que existe, o que foi usado e por quê.
- [`docs/01-instalacao.md`](docs/01-instalacao.md): instalação passo a passo (dev e produção).
- [`docs/02-preparar-o-banco.md`](docs/02-preparar-o-banco.md): criar o usuário read-only
  e liberar a rede, em cada banco.
- [`docs/03-arquitetura.md`](docs/03-arquitetura.md): como as peças se encaixam.
- [`docs/04-troubleshooting.md`](docs/04-troubleshooting.md): erros comuns e o que fazer.
- [`docs/DESIGN.md`](docs/DESIGN.md): o design completo do produto.

## Licença

[MIT](LICENSE).
