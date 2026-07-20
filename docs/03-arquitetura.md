# 03 — Arquitetura

Resumo prático. O design completo está em [`DESIGN.md`](DESIGN.md).

## Ideia central

Um núcleo isolado, as regras mais o acesso ao banco, com uma casca MCP por cima. O núcleo
não sabe nada sobre o transporte (stdio ou HTTP): recebe uma chamada, roda os guardrails e
executa a query. Por isso dá pra exercitar a lógica nos testes sem subir servidor nem falar
com um cliente MCP.

```
Cliente MCP / Agente  ──MCP (stdio ou HTTP+token)──▶  server.py (FastMCP)
                                                          │  chama o núcleo
                                                          ▼
                                    guardrails/ (Cadeado nº 3)  +  config.py
                                    valida SELECT · allowlist       observability.py
                                    LIMIT · teto · rate limit       (logs + auditoria)
                                                          │  só passa SQL aprovado
                                                          ▼
                                                        db.py (fachada) → dialeto
                                                        (pool psycopg 3, READ ONLY + timeout)
                                                          │
                                                          ▼
                                                   PostgreSQL do cliente
                                          usuário read-only (Cadeado nº 1)
                                          pg_hba por IP   (Cadeado nº 2)
```

## Componentes (`src/db_mcp/`)

| Arquivo | Responsabilidade |
|---|---|
| `config.py` | Carrega `.env` (segredos) + `config.yaml` via `pydantic-settings`; valida na subida. |
| `db.py` | Fachada fina de acesso ao banco; delega ao dialeto (pool, cursor-dict, tradução de erro do driver). Não importa `psycopg` — o núcleo é dialeto-agnóstico. |
| `dialetos/` | `base.py` = contrato `Dialeto` (o `Protocol`, sem driver); `postgres.py` = pool `psycopg` 3 em transação `READ ONLY` + timeout, `DISCARD ALL` no reset, lista de funções perigosas. MySQL e SQL Server entram aqui (fases 1 e 2). |
| `guardrails/sql.py` | Cadeado nº 3 (a): valida que é `SELECT`, uma instrução, sem funções perigosas. |
| `guardrails/policy.py` | Allowlist de tabelas + injeção de `LIMIT`. |
| `guardrails/ratelimit.py` | Rate limit token-bucket por cliente, thread-safe. |
| `server.py` | FastMCP; define as ferramentas, chama guardrails→db, traduz erros. |
| `observability.py` | Logging estruturado + trilha de auditoria (uma linha JSON por consulta, inclusive as recusadas), thread-safe. |
| `cli.py` | `run` (sobe o servidor, padrão) e `doctor` (verificação). |
| `doctor.py` | Motor de checagens + as 6 checagens de saúde/preflight. |

## Ferramentas (`server.py`)

O núcleo (`consultar`) roda os guardrails na ordem: rate limit, validação só-leitura,
allowlist (opcional), injeção de `LIMIT`, teto de bytes no resultado. Cada ferramenta MCP é
uma casca fina por cima disso:

- `listar_schemas()`, `listar_tabelas(schema="public")`, `listar_views(schema="public")` e
  `descrever_tabela(tabela, schema="public")` são introspecção. Rodam SQL fixo em
  `information_schema` e chamam o núcleo com `aplicar_allowlist=False`: metadados são
  listáveis sem allowlist, o que passa pela allowlist são os dados de linha. O nome de
  schema/tabela é interpolado na query, então cada uma valida o identificador antes
  (`_validar_ident` / `_validar_qualificado`). `descrever_tabela` devolve `column_name`,
  `data_type` e `is_nullable`.
- `amostra(tabela, n=10)` faz `SELECT * ... LIMIT n` da tabela e passa pela allowlist; `n`
  é limitado ao teto de linhas da config (e nunca fica negativo).
- `consultar(sql)` executa um `SELECT` do cliente, com allowlist. Só é registrada quando
  `ALLOW_FREEFORM_SQL=true`; com `false`, a ferramenta nem existe.

`amostra` e `consultar` devolvem `{"linhas", "truncado", "total"}`: `total` é a contagem de
linhas **devolvidas** (não da tabela inteira), e `truncado` diz se havia mais linhas além do
teto — quando `truncado` é `true`, o resultado foi cortado.

Erros tratados viram um `codigo` estável (`sql_invalido`, `somente_leitura`,
`fora_da_allowlist`, `limite_de_taxa`, `resultado_grande_demais`, `timeout`, `erro_banco`),
definido em [`errors.py`](../src/db_mcp/errors.py). Toda consulta vira uma linha na
auditoria — as que passam com `veredito` `ok`, as recusadas com o código do erro. As
ferramentas que devolvem dados (`amostra`, `consultar`) entregam esse código num objeto
`{"erro", "detalhe"}`; as de introspecção, que devolvem listas, propagam o erro.

O rate limit e a auditoria são "por cliente". Cliente aqui é o `client_id` do token no
transporte HTTP; sem request autenticada (stdio, testes), tudo cai em `stdio`. Como o servidor
usa um único `AUTH_TOKEN`, na prática todo o tráfego HTTP compartilha o mesmo balde — a
separação real hoje é entre HTTP e stdio.

## Os 3 cadeados (defesa em profundidade)

Os números no diagrama acima são as três camadas de defesa. O cadeado nº 1 é o usuário
só-leitura no banco; o nº 2 é o `pg_hba` liberando só IPs conhecidos; ambos são configuração
de infra (ver [`docs/02`](02-preparar-o-banco.md)). O nº 3 é o código deste repo, dentro de
`guardrails/`: validação de SQL, allowlist, limites de linhas e bytes, rate limit. As três
camadas são independentes: se uma falha, a próxima ainda segura.

Parâmetros e o porquê de cada uma em [`DESIGN.md`](DESIGN.md) §5 e §6.
