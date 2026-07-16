# Visão geral

O projeto em linguagem direta: o que ele é, o problema que resolve, como funciona por dentro e
o que ele expõe. Se você quer só instalar, vá pro [README](../README.md); aqui a ideia é
_entender_. Para uma explicação do zero, sem pressupor conhecimento técnico, veja
[`00-para-leigos.md`](00-para-leigos.md).

## O que é, em uma frase

Um servidor MCP que deixa um agente de IA (Claude Desktop, Claude Code, uma automação)
**ler** um banco PostgreSQL — listar tabelas, ver colunas, rodar `SELECT` — sem nenhuma
chance de escrever, alterar ou derrubar o banco.

## O problema que ele resolve

Dar a um agente de IA acesso ao banco é útil e perigoso ao mesmo tempo. Útil, porque o agente
responde perguntas sobre os dados sozinho. Perigoso, porque um modelo de linguagem é
imprevisível: basta um `DROP TABLE` alucinado, um `UPDATE` sem `WHERE`, ou uma query que puxa
dez milhões de linhas e trava tudo.

O db-mcp **assume que o agente vai errar e deixa o caminho seguro mesmo assim.** Se o
modelo tentar escrever, o banco recusa; se pedir uma tabela que não devia, a aplicação barra;
se pedir linhas demais, existe um teto.

## Como funciona: os três cadeados

A segurança não depende de uma peça só. São três camadas independentes — se uma falha, a
próxima ainda segura. Duas são configuração de infraestrutura; a terceira é o código deste
repositório.

1. **No banco (cadeado nº 1).** Um usuário dedicado que só tem `GRANT SELECT` e roda com
   `default_transaction_read_only = on`. O próprio PostgreSQL recusa qualquer escrita vinda
   dele. É a defesa mais forte, porque não depende do nosso código estar certo.
2. **Na rede (cadeado nº 2).** O `pg_hba.conf` do Postgres libera esse usuário só a partir dos
   IPs conhecidos (sua máquina, o servidor do MCP). Quem não está na faixa nem conecta.
3. **Na aplicação (cadeado nº 3).** Antes de qualquer query tocar o banco, o código valida:
   é mesmo um `SELECT`? uma instrução só? a tabela está liberada? tem `LIMIT`? passou do teto
   de linhas ou de bytes? estourou o rate limit? No HTTP, o token confere? Só depois de tudo
   isso a query roda.

A allowlist do cadeado 3 leva a sério a distinção de schema: uma entrada `public.clientes`
libera exatamente aquela tabela, e trocar o schema (`secret.clientes`) não fura.

## As peças do código

Tudo vive em `src/db_mcp/`. O desenho é um **núcleo isolado** — as regras mais o
acesso ao banco — com uma casca MCP fina por cima. O núcleo não sabe se está falando stdio ou
HTTP; recebe uma chamada, roda os guardrails, executa. Por isso a lógica toda é testável sem
subir servidor nem falar com um cliente MCP de verdade.

| Peça | O que faz |
|---|---|
| `config.py` | Lê `.env` (segredos) e `config.yaml` (ajustes) e valida na subida — falha cedo se algo estiver errado. |
| `db.py` | Pool de conexões; toda query roda em transação `READ ONLY` com timeout. |
| `guardrails/sql.py` | O validador: aceita só `SELECT`, uma instrução, sem DDL/escrita nem funções perigosas. |
| `guardrails/policy.py` | A allowlist de tabelas e a injeção automática de `LIMIT`. |
| `guardrails/ratelimit.py` | O rate limit (token-bucket), para uma rajada de queries não afogar o banco. |
| `server.py` | A casca FastMCP: define as seis ferramentas e chama o núcleo. |
| `observability.py` | Logs e a trilha de auditoria (uma linha por consulta, inclusive as recusadas). |
| `errors.py` | As exceções tratadas, cada uma com um código estável. |
| `cli.py` + `doctor.py` | Sobe o servidor (`run`) e o `doctor`, que verifica se está tudo no lugar. |

## O que o agente pode fazer: as seis ferramentas

- `listar_schemas()`, `listar_tabelas(schema)`, `listar_views(schema)`,
  `descrever_tabela(tabela)` — introspecção: o agente descobre o que existe no banco.
- `amostra(tabela, n)` — as primeiras N linhas de uma tabela liberada.
- `consultar(sql)` — um `SELECT` livre, validado e limitado. Dá pra desligar
  (`ALLOW_FREEFORM_SQL=false`) e deixar só a introspecção e a amostra.

A introspecção lê metadados livremente; a allowlist só entra nas ferramentas que trazem linhas
de dados (`amostra` e `consultar`).

## As tecnologias

- **FastMCP** — fala o protocolo MCP, com stdio e HTTP prontos e um verificador de token Bearer
  embutido.
- **psycopg 3** — o driver PostgreSQL, com pool de conexões nativo e o modo `read_only` por
  conexão, que reforça o cadeado nº 1 do lado da aplicação.
- **sqlglot** — um parser de SQL em Python puro. É a peça-chave da segurança: em vez de barrar
  comandos perigosos com expressão regular (frágil), a query é **transformada em árvore** e
  inspecionada de verdade. Por ser Python puro, instala em qualquer sistema operacional sem
  compilador.
- **pydantic-settings** — carrega e valida a configuração de `.env` + `config.yaml` com tipos,
  falhando na subida se faltar algo, em vez de quebrar no meio de uma query.
- **uv** — o gerenciador de pacotes/venv, com lockfile reprodutível.

## Como instalar (resumo)

O passo a passo completo está em [`01-instalacao.md`](01-instalacao.md); o preparo do banco em
[`02-preparar-o-banco.md`](02-preparar-o-banco.md). Em resumo:

```bash
uv sync                       # instala tudo
cp .env.example .env          # preencha host, banco, senha do usuário read-only
uv run db-mcp doctor # verifica config, rede, auth, read-only, allowlist, latência
uv run db-mcp        # sobe o servidor (stdio)
```

Para ver funcionando sem preparar banco nenhum, a seção **"Experimente em 30 segundos"** do
README sobe um Postgres de demonstração em Docker, já semeado e com o usuário read-only pronto.

O jeito mais fácil de configurar contra o _seu_ banco é deixar o Claude conduzir: abra a pasta
no Claude Code e siga o [`SETUP.md`](../SETUP.md) — uma skill pergunta os parâmetros, ajuda a
criar o usuário read-only, preenche a config e registra o MCP no cliente.

## O `doctor`: a prova de que está tudo certo

Antes de plugar num agente, `db-mcp doctor` roda seis checagens e diz, uma a uma, o que
passou e o que fazer se falhar: config válida, TCP alcança o host, autentica como o usuário
read-only, **confirma que é read-only de verdade** (tenta uma escrita e espera levar não),
tabelas da allowlist existem, e a latência de uma query trivial. Sai com código `0` se tudo
passar.

## O que ele deliberadamente não faz

Escrever no banco (nunca), falar com outros bancos além de PostgreSQL, ou embutir consultas de
negócio prontas. O objetivo é ser uma ferramenta genérica e segura de leitura.
