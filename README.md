# pg-readonly-mcp

[![CI](https://github.com/brunocmattos/pg-readonly-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/brunocmattos/pg-readonly-mcp/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://img.shields.io/badge/mypy-strict-blue)](https://mypy-lang.org/)

Servidor MCP somente-leitura para PostgreSQL. Dá a agentes de IA (Claude Desktop,
Claude Code, automações) acesso de introspecção e `SELECT` a tabelas e views, sem
escrever, alterar schema ou derrubar o banco.

O código não conhece nenhum banco específico: você aponta o MCP pro seu Postgres
preenchendo a config. Nenhum host, senha ou nome de tabela real fica no repositório.

## Os três cadeados

Defesa em profundidade, três camadas independentes — se uma falha, a próxima ainda segura.
As duas primeiras são configuração de infra; a terceira é o código deste repo.

1. No banco: um usuário dedicado com apenas `GRANT SELECT` e
   `default_transaction_read_only = on`. O próprio Postgres recusa escrita.
2. Na rede: `pg_hba.conf` libera esse usuário só das faixas de IP conhecidas.
3. Na aplicação: o validador SQL (`sqlglot`: só `SELECT`, uma instrução, sem funções
   perigosas), allowlist de tabelas, `LIMIT` automático, teto de linhas/bytes, rate limit
   e, no transporte HTTP, autenticação por token Bearer.

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

Não precisa de um Postgres seu. O `docker-compose.yml` sobe um banco já semeado e
com o usuário read-only `mcp_ro` pronto:

```bash
docker compose up -d                            # Postgres de demo na porta 5433
uv sync                                          # instala o MCP
uv run pg-readonly-mcp --env .env.demo doctor    # confere tudo
```

Saída (real, contra o container acima):

```text
== pg-readonly-mcp doctor ==
✅ [OK] Config OK  —  mcp_ro@localhost:5433/demo · allowlist=['*']
✅ [OK] TCP OK  —  conectou em 9 ms
✅ [OK] Autenticou  —  current_user=mcp_ro · db=demo
✅ [OK] Somente-leitura confirmado  —  write recusado: 25006 ReadOnlySqlTransaction
✅ [OK] Allowlist = todas (*)  —  nada específico a verificar
✅ [OK] Latência SELECT 1  —  mediana 0.4 ms (min 0.4 · max 0.6)

6 ok · 0 falha(s) · 0 pulada(s)
```

Repare no quarto check: o próprio banco recusa a escrita de teste. Uma consulta
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

Para subir o servidor apontado nesse banco: `uv run pg-readonly-mcp --env .env.demo`.
Para desligar e apagar tudo: `docker compose down -v`.

## Instalação

Requer Python 3.11+ e o gerenciador [`uv`](https://docs.astral.sh/uv/) (testado com 3.12
e 3.13). O pacote não está publicado no PyPI: instala-se clonando o repo e rodando `uv sync`.

Passo a passo na mão em [`docs/01-instalacao.md`](docs/01-instalacao.md). Para deixar o
Claude conduzir, abra esta pasta no Claude Code e siga [`SETUP.md`](SETUP.md): uma skill
pergunta os parâmetros do seu banco, ajuda a criar o usuário read-only, preenche a config,
roda a verificação e registra o MCP no cliente.

Resumo (na mão):

```bash
uv sync                       # instala tudo
cp .env.example .env          # preencha PG_HOST/PG_DBNAME/PG_PASSWORD...
uv run pg-readonly-mcp doctor # verifica config, rede, auth, read-only, allowlist, latencia
uv run pg-readonly-mcp        # sobe o servidor (stdio)
```

O `doctor` só fica verde com o banco já preparado (usuário `mcp_ro` +
`pg_hba`, ver [`docs/02-preparar-o-banco.md`](docs/02-preparar-o-banco.md)). Sem esse
passo, as checagens de auth e de read-only falham.

## Verificação

`uv run pg-readonly-mcp doctor` roda 6 checagens (config válida, TCP alcança o host,
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
- [`docs/02-preparar-o-banco.md`](docs/02-preparar-o-banco.md): criar o usuário read-only e o `pg_hba`.
- [`docs/03-arquitetura.md`](docs/03-arquitetura.md): como as peças se encaixam.
- [`docs/04-troubleshooting.md`](docs/04-troubleshooting.md): erros comuns e o que fazer.
- [`docs/DESIGN.md`](docs/DESIGN.md): o design completo do produto.

## Licença

[MIT](LICENSE).
