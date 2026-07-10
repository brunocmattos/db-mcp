# pg-readonly-mcp: documento de design

> Design do produto: um servidor MCP somente-leitura, genérico, para qualquer PostgreSQL.

---

## 0. Produto (genérico/público) vs Deployment (específico/privado)

Este projeto tem duas camadas que nunca se misturam.

| Camada | O que é | Onde vive | Vai pro GitHub? |
|---|---|---|---|
| Produto | O código do MCP mais os docs de como preparar, instalar e usar qualquer Postgres. Exemplos sempre com placeholders (`SEU_HOST`, `SUA_PORTA`, `SUA_SENHA`). | o repositório | sim, público |
| Deployment | A config real de um ambiente (host, porta, senha, allowlist) e o registro de como aquele ambiente foi preparado. | `.env` / `config.yaml` + `deployments/<ambiente>.md` | não, git-ignored |

O código não conhece nenhum banco específico; sabe acessar um Postgres dentro das restrições
configuradas. Quem clona o repositório aponta o MCP pro próprio banco preenchendo a config. O
nosso primeiro ambiente é só o primeiro deployment, e mora num arquivo privado que nunca sobe
pro GitHub.

Nenhum IP, hostname, senha ou nome de tabela real entra no repositório. Valores concretos que
aparecem no código ou nos docs públicos são placeholders.

---

## 1. O que é

Um servidor MCP que dá acesso somente-leitura a um PostgreSQL (tabelas e views) para agentes de
IA (Claude Desktop, Claude Code, qualquer cliente MCP) e automações. É genérico: qualquer
Postgres, via config. Nenhuma consulta de negócio fica hardcoded; tudo passa por parâmetro.

### Objetivos
- Acesso read-only a tabelas e views de um Postgres qualquer.
- Um agente não escreve, não derruba o banco nem estoura memória/tokens da máquina (as restrições estão em §5).
- Fala o protocolo MCP, por transporte local (stdio) ou remoto (HTTP).
- Instalável na mão (manual) ou com o Claude conduzindo (skill).
- Verificação de erros, logs de auditoria e testes automatizados.

### Não-objetivos
- Escrita no banco (INSERT/UPDATE/DELETE/DDL): nunca.
- Consultas de negócio nomeadas.
- Múltiplos bancos numa mesma instância (1 database por instância).
- Outros SGBDs além de PostgreSQL.

---

## 2. Públicos e modos de instalação

| Modo | Para quem | Como funciona |
|---|---|---|
| Manual | Pessoa configurando na mão | `README.md` + `docs/` com passo a passo genérico: pré-requisitos, criar usuário read-only, liberar rede (`pg_hba`), instalar deps, preencher config, rodar, plugar no cliente, troubleshooting. |
| Assistido (Claude) | Quem tem o Claude Code | `SETUP.md` + uma skill que o Claude lê e executa: pergunta os parâmetros do seu banco, ajuda a criar o usuário, preenche a config, registra o MCP no cliente e roda a verificação. |
| Terminal | Quem prefere linha de comando | Clonar o repo, `uv sync`, `uv run pg-readonly-mcp doctor` para validar, `uv run pg-readonly-mcp` para subir. |

---

## 3. Arquitetura

Núcleo isolado (regras + acesso ao banco) com uma "casca" MCP por cima. Os módulos são
separados e dá pra testar cada um sozinho, sem subir o servidor.

```
   Cliente MCP / Agente
   (Claude Desktop, Code, automações)
            │
            │  MCP (stdio  ou  HTTP+token)
            ▼
   ┌─────────────────────────────────────────────┐
   │              server.py  (FastMCP)            │  ← casca: expõe as ferramentas
   │   listar_schemas · listar_tabelas · views    │
   │   descrever_tabela · amostra · consultar     │
   └───────────────┬─────────────────────────────┘
                   │ chama o núcleo
                   ▼
   ┌──────────────────────┐   ┌──────────────────────┐
   │   guardrails/        │   │      config.py        │
   │  (CADEADO nº 3)      │   │  parâmetros + secrets │
   │  • valida SELECT     │   └──────────────────────┘
   │   (parser sqlglot)   │
   │  • allowlist         │   ┌──────────────────────┐
   │  • LIMIT automático  │   │   observability.py    │
   │  • teto linhas/bytes │   │  logs + auditoria     │
   │  • rate limit        │   └──────────────────────┘
   └──────────┬───────────┘
              │ só passa SQL já aprovado
              ▼
   ┌──────────────────────┐
   │        db.py         │  pool de conexões (psycopg 3)
   │  usuário read-only   │  transação READ ONLY + statement_timeout
   └──────────┬───────────┘
              │ TCP (só as faixas liberadas no pg_hba do alvo)
              ▼
        PostgreSQL do cliente
        usuário read-only = FISICAMENTE só-leitura   ← CADEADO nº 1
        pg_hba libera só IPs conhecidos              ← CADEADO nº 2
```

### Componentes
- `config.py`: carrega parâmetros de `.env` (segredos) e `config.yaml` (o resto), via
  `pydantic-settings`. Valida na inicialização, falhando cedo se algo estiver errado.
- `db.py`: pool `psycopg` 3. Toda query roda em transação `READ ONLY` com `statement_timeout`.
- `guardrails/`: o cadeado nº 3 (§5), separado em `sql.py` (validação), `policy.py` (allowlist
  + `LIMIT`) e `ratelimit.py`. Sem I/O.
- `server.py`: FastMCP. Define as ferramentas, chama guard→db, traduz exceções em erros legíveis.
- `observability.py`: logging estruturado e trilha de auditoria.
- `errors.py`: as exceções tratadas, cada uma com um `codigo` estável.
- `cli.py` + `doctor.py`: `run` (sobe o servidor) e `doctor` (verificação, §8).

---

## 4. Ferramentas MCP expostas (genéricas)

| Ferramenta | Entrada | Saída | Passa pela allowlist? |
|---|---|---|---|
| `listar_schemas()` | — | nomes dos schemas visíveis | não |
| `listar_tabelas(schema="public")` | schema (default `public`) | nomes das tabelas do schema | não |
| `listar_views(schema="public")` | schema (default `public`) | nomes das views do schema | não |
| `descrever_tabela(tabela, schema="public")` | tabela + schema | colunas: `column_name`, `data_type`, `is_nullable` | não |
| `amostra(tabela, n=10)` | tabela, N (≤ `MAX_ROWS`) | primeiras N linhas (`SELECT * … LIMIT N`) | sim |
| `consultar(sql)` | uma query `SELECT` | linhas (dentro dos tetos) | sim |

A introspecção (`listar_schemas`, `listar_tabelas`, `listar_views`, `descrever_tabela`) lista
metadados e não aplica allowlist. É uma decisão explícita: listar schema, tabela e coluna é
liberado; os dados de linha, via `amostra` e `consultar`, é que passam pela allowlist de
tabelas. `descrever_tabela` devolve só `column_name`, `data_type` e `is_nullable` (não traz
PK/FK nem comentários).

`consultar(sql)` pode ser desligado por config (`ALLOW_FREEFORM_SQL=false`), deixando só a
introspecção e o `amostra`.

---

## 5. Segurança: os 3 cadeados (defesa em profundidade)

Mesmo que um cadeado falhe, o próximo segura. Os cadeados 1 e 2 são passos de deployment (cada
ambiente configura o seu, documentado no manual genérico). O cadeado 3 é código do produto.

### Cadeado nº 1: banco fisicamente só-leitura (passo de deployment)
Um usuário dedicado read-only no Postgres do cliente:
- `default_transaction_read_only = on`: escrita recusada pelo próprio Postgres.
- Só `GRANT SELECT` (nenhum privilégio de escrita, não é superuser nem dono de tabela).
- `statement_timeout` e `idle_in_transaction_session_timeout` cortam query longa.
- `CONNECTION LIMIT` para não monopolizar o banco.

O manual (`docs/02-preparar-o-banco.md`) ensina a criar esse usuário com placeholders.

### Cadeado nº 2: rede (passo de deployment)
Regras `pg_hba.conf` liberam o usuário read-only apenas das faixas de IP conhecidas (máquina de
dev, servidor do MCP). O manual explica como.

### Cadeado nº 3: aplicação (código do produto)
Antes de tocar o banco:
- Validador SQL com `sqlglot` (parser SQL em Python puro): aceita só `SELECT`/`WITH…SELECT`,
  uma instrução por vez (bloqueia `;` empilhado), e rejeita DML/DDL, `SELECT … INTO`,
  `FOR UPDATE/SHARE`, e funções perigosas ou com efeito colateral (`pg_read_file`,
  `COPY … TO/FROM`, `dblink`, `nextval/setval` etc.).
- Allowlist de tabelas/views: a query só passa se tocar objetos liberados na config (vale para
  `amostra` e `consultar`; a introspecção não passa por aqui). Uma entrada qualificada
  (`schema.tabela`) libera só aquele par exato — não dá pra burlar trocando o schema; uma
  entrada sem schema (`tabela`) libera aquele nome em qualquer schema.
- `LIMIT` automático até o teto `MAX_ROWS`.
- Rejeição de resultados acima de `MAX_RESULT_BYTES` (recusa a consulta; não trunca).
- Rate limit de `RATE_LIMIT_PER_MIN` por cliente (token-bucket, thread-safe).
- No transporte HTTP, o servidor valida `Authorization: Bearer <token>` em toda requisição
  (via `StaticTokenVerifier` do FastMCP) e recusa subir sem `AUTH_TOKEN` configurado
  (fail-closed). O stdio não usa auth.

**A allowlist é defesa em profundidade, não o limite último.** Ela analisa o SQL pra barrar
tabelas fora da lista, e o validador bloqueia as funções conhecidas que a driblariam (ex.: os
`*_to_xml`, `set_config`, advisory locks, `pg_logical_emit_message`). Mas nenhuma análise de SQL
na aplicação é à prova de tudo contra um role com privilégios amplos: sempre há mais uma função.
O que a análise de SQL **não** cobre por completo: metadados (`pg_relation_size`,
`pg_get_viewdef` revelam existência/tamanho/DDL de objetos fora da allowlist) e o pico de memória
de um resultado muito largo (ex.: `repeat('x', 5e8)` ou `lpad(...)` montam uma única linha
gigante — o teto de bytes é checado depois de materializar, e `MAX_ROWS`/`LIMIT` limitam a
contagem de linhas, não a largura de cada uma). O `statement_timeout` corta o caso mais extremo;
fechar de vez exigiria um cursor server-side com contagem incremental de bytes.

Para isolamento realmente forte, **o limite tem que estar no banco** (cadeado nº 1), não só na
aplicação: em vez de `SELECT` amplo, dê ao `mcp_ro` `GRANT SELECT` só nas tabelas/views que ele
deve ver, e `REVOKE` a execução de funções perigosas. Aí o próprio PostgreSQL recusa o resto,
por mais esperto que seja o SQL. Ver [`02-preparar-o-banco.md`](02-preparar-o-banco.md). O reset
da conexão no pool (`DISCARD ALL`) fecha outro flanco: nenhum estado de sessão (GUC, advisory
lock) vaza de um cliente pro próximo.

---

## 6. Parâmetros de configuração

Segredos em `.env`; o resto em `config.yaml`. Todos os parâmetros têm default e são validados na
subida. Os valores abaixo são placeholders; cada deployment preenche com os seus.

| Parâmetro | Onde | Default | Descrição |
|---|---|---|---|
| `PG_HOST` | .env | — | host do Postgres alvo |
| `PG_PORT` | .env | `5432` | porta |
| `PG_DBNAME` | .env | — | banco alvo |
| `PG_USER` | .env | `mcp_ro` | usuário read-only |
| `PG_PASSWORD` | .env | — | segredo |
| `PG_SSLMODE` | .env | `prefer` | modo TLS |
| `TRANSPORT` | yaml | `stdio` | `stdio` ou `http` |
| `HTTP_HOST` / `HTTP_PORT` | yaml | `127.0.0.1` / `8080` | quando `http` |
| `AUTH_TOKEN` | .env | — | segredo, exigido no transporte `http` |
| `ALLOWLIST` | yaml | `["*"]` | schemas/tabelas liberados (`*` = todos) |
| `ALLOW_FREEFORM_SQL` | yaml | `true` | liga/desliga a ferramenta `consultar` |
| `MAX_ROWS` | yaml | `1000` | teto de linhas por consulta |
| `MAX_RESULT_BYTES` | yaml | `1000000` | teto do payload de resposta |
| `STATEMENT_TIMEOUT_MS` | yaml | `5000` | timeout por query (app + sessão) |
| `RATE_LIMIT_PER_MIN` | yaml | `60` | consultas/min por cliente |
| `POOL_MIN` / `POOL_MAX` | yaml | `1` / `5` | pool de conexões |
| `LOG_LEVEL` | yaml | `INFO` | nível de log |
| `AUDIT_LOG_PATH` | yaml | `./audit.log` | trilha de auditoria |

Acompanham `.env.example` e `config.example.yaml`, só com placeholders.

---

## 7. Transporte e deployment

- Dev (máquina local): `TRANSPORT=stdio`, conecta no banco alvo pela rede/VPN, plugado no
  Claude Code/Desktop local. Nesse modo não há auth.
- Produção (servidor): `TRANSPORT=http` com `AUTH_TOKEN` obrigatório (o servidor não sobe sem
  ele), rodando como serviço `systemd` (`pg-readonly-mcp.service`). Agentes e automações
  conectam pela rede.
- Registro no cliente: o `SETUP.md` e a skill geram o trecho de config do cliente MCP.

---

## 8. Verificação e tratamento de erros

`pg-readonly-mcp doctor` roda seis checagens e, em cada uma, diz o que passou e o que fazer se
falhar: 1. config carregada e válida; 2. TCP alcança host:porta; 3. autentica como o usuário
read-only; 4. confirma read-only (tenta um write e espera que falhe); 5. tabelas da allowlist
existem; 6. mede a latência de uma query trivial. As checagens de auth e de read-only só passam
com o banco já preparado (§5, cadeados 1 e 2).

Erros legíveis pro agente: `SqlInvalido`, `SomenteLeitura`, `ForaDaAllowlist`, `LimiteDeTaxa`,
`ResultadoGrandeDemais`, `ConsultaTimeout`, `ErroBanco` (cada um com um `codigo` estável). A
falha de token no transporte HTTP é tratada pelo próprio FastMCP (responde `401` antes da
ferramenta rodar), então não vira um desses códigos.

Cada consulta é logada (origem, SQL, nº de linhas, duração, veredito). Testes com `pytest` e
GitHub Actions no push.

---

## 9. Estrutura do repositório (o que é público vs privado)

```
pg-readonly-mcp/
├── README.md                 # PÚBLICO — visão geral + índice do manual
├── LICENSE                   # PÚBLICO — MIT
├── pyproject.toml            # PÚBLICO
├── .env.example              # PÚBLICO — só placeholders
├── config.example.yaml       # PÚBLICO — só placeholders
├── SETUP.md                  # PÚBLICO — modo assistido (Claude)
├── CONTRIBUTING.md · SECURITY.md · CHANGELOG.md   # PÚBLICO
├── docker-compose.yml         # PÚBLICO — Postgres de demonstração
├── .env.demo                  # PÚBLICO — credenciais FAKE da demo
├── demo/                      # PÚBLICO — schema/seed/usuário read-only da demo
├── .claude/skills/setup-pg-readonly-mcp/SKILL.md   # PÚBLICO
├── docs/                     # PÚBLICO — manual genérico (placeholders)
│   ├── VISAO-GERAL.md
│   ├── DESIGN.md
│   ├── 01-instalacao.md
│   ├── 02-preparar-o-banco.md    # runbook GENÉRICO: usuário read-only + pg_hba
│   ├── 03-arquitetura.md
│   └── 04-troubleshooting.md
├── src/pg_readonly_mcp/       # PÚBLICO — o código genérico
│   ├── (config, db, server, observability, cli, doctor, errors).py + py.typed
│   └── guardrails/ (sql, policy, ratelimit).py
├── tests/                     # PÚBLICO
├── .github/workflows/ci.yml   # PÚBLICO
├── deployments/               # aqui mora o específico de cada ambiente
│   ├── README.md              #   PÚBLICO — explica o padrão
│   ├── _template.md           #   PÚBLICO — modelo em branco
│   └── <ambiente>.md          #   PRIVADO — git-ignored, NUNCA sobe
├── .env                       # PRIVADO — git-ignored
└── config.yaml                # PRIVADO — git-ignored
```

O `.gitignore` bloqueia `.env`, `config.yaml`, `*.cred` e `deployments/*` (exceto o `README.md`
e o `_template.md`). Assim, o repositório público só contém o produto genérico.
