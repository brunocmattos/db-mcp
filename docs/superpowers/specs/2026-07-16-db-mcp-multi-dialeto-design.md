# db-mcp: design multi-dialeto (v0.3)

> De `pg-readonly-mcp` (só PostgreSQL) para `db-mcp`: um repo, um pacote, três dialetos
> como módulos. Escopo deste spec: **somente leitura**. Escrita ganha spec próprio.

Data: 2026-07-16 · Repo: `github.com/brunocmattos/db-mcp` (renomeado; a URL antiga redireciona)

---

## 0. Por que este documento existe

O `DESIGN.md` atual lista, com todas as letras, dois não-objetivos que este spec derruba:

> - Escrita no banco (INSERT/UPDATE/DELETE/DDL): nunca.
> - Outros SGBDs além de PostgreSQL.

O segundo cai agora (MySQL e SQL Server entram). O primeiro cai **depois**, em spec próprio —
mas o nome do repo já mudou para `db-mcp` porque `readonly` no nome viraria mentira quando
aquele dia chegar.

Este spec cobre **só o eixo dialeto**. Escrita é o eixo permissão, e misturar os dois significa
que, quando algo quebrar, não saberemos qual dos dois quebrou.

---

## 1. Decisões e o que foi descartado

| # | Decisão | Descartado | Por quê |
|---|---|---|---|
| 1 | **Um repo** (`db-mcp`), dialetos como módulos | 3 repos separados; núcleo-lib + 3 pacotes | Com 3 repos a lista de funções perigosas **diverge**: você corrige um bypass no Postgres e esquece nos outros dois. Segurança triplicada apodrece. Núcleo-lib exigiria PyPI (o pacote não está publicado) e versionamento cruzado. |
| 2 | **Pool nativo por dialeto** | SQLAlchemy Core; `DBUtils.PooledDB` | `DBUtils` só faz `rollback` ao devolver a conexão e **não deixa rodar `DISCARD ALL`** — que aqui é segurança, não higiene. SQLAlchemy resolveria, mas é dependência grande num produto cuja tese é superfície pequena, e tiraria o Postgres do caminho já provado. O `configure`/`reset` é por dialeto de qualquer jeito. |
| 3 | **pymssql** para SQL Server | pyodbc | pyodbc exige `msodbcsql18` instalado no SO (no Linux é repo da Microsoft + EULA) — quebra a promessa de "clona e roda" de um produto público. Custo aceito: sem Entra ID nem Always Encrypted. |
| 4 | **mysql-connector-python** para MySQL | PyMySQL | Consequência da decisão 2: precisamos de pool nativo **e** de `RESET CONNECTION`. O `mysql-connector` tem os dois (`pooling.MySQLConnectionPool` e `cnx.reset_session()`); o PyMySQL não tem nenhum. |
| 5 | **Só leitura neste spec** | dialeto × permissão juntos | Eixos ortogonais. Escrita tem perguntas que não são destas: permissão por tabela ou por operação? confirmação humana? auditoria vira obrigatória? Merece brainstorm próprio. |

### Princípio que vale mesmo no futuro com escrita

**O cadeado nº 1 é a autoridade. A configuração da aplicação só pode subtrair do que o
usuário do banco já pode fazer — nunca somar.**

`MODE=write` apontado num `mcp_ro` continua não escrevendo: o Postgres recusa, e ponto.
Escrita real exigirá um **usuário de banco diferente, com GRANT de escrita** — passo
deliberado de deployment, não uma linha de YAML. Assim o futuro com escrita mantém defesa em
profundidade em vez de virar um gateway com um booleano na frente.

Consequência para este spec: `validar_somente_leitura(sql)` vira `validar(sql, dialeto, perfil)`.
O parâmetro `perfil` nasce com um único valor (`SOMENTE_LEITURA`) e **não** ganha modelo de
permissões agora. É a costura no lugar certo, não a feature.

---

## 2. Evidência: o que porta e o que não porta

Medido contra `sqlglot 30.12.0`, não presumido.

**Porta sem mudança (o núcleo é dialeto-agnóstico):**

| Peça | PostgreSQL | MySQL | SQL Server |
|---|---|---|---|
| `TAGS_PROIBIDAS` (`Insert`/`Update`/`Delete`/`Create`/`Drop`) | nomes de nó **idênticos** | idênticos | idênticos |
| Funções perigosas via `exp.Anonymous` | `pg_read_file` | `load_file`, `sleep`, `benchmark` | `openquery` |
| `;` empilhado | barrado | barrado | barrado |
| Transpilação de `LIMIT` | `LIMIT n` | `LIMIT n` | vira `TOP n` sozinho |

**Falha fechado (ParseError → `SqlInvalido`), que é o lado certo:**
`SELECT ... INTO OUTFILE` (MySQL grava arquivo) e `WAITFOR DELAY` (DoS no T-SQL) não fazem
parse. Barrados por acidente feliz — mas **por acidente**: um upgrade do sqlglot que passe a
parsear qualquer um dos dois abre o buraco em silêncio. Vira teste de regressão (§8).

**Barrado pelo check de raiz:** `EXEC xp_cmdshell` e `EXECUTE sp_who` viram raiz `Execute`,
que não é `Select`/`SetOperation` → `SomenteLeitura`.

**Passa pelo validador atual e PRECISA entrar na lista do T-SQL:**
`OPENQUERY`, `OPENROWSET`, `OPENDATASOURCE` — todos com raiz `Select`. Executam SQL vindo de
string e escapam da allowlist, exatamente como os `*_to_xml` do Postgres.

---

## 3. Arquitetura: o contrato `Dialeto`

O que muda entre bancos é uma superfície pequena e enumerável. Tudo o mais (`server.py`,
`ratelimit.py`, `observability.py`, `errors.py`, a estrutura de `policy.py`) continua sem saber
qual banco está do outro lado.

```
src/db_mcp/
├── config.py          # + dialeto: Literal["postgres","mysql","sqlserver"]
├── server.py          # casca MCP — dialeto-agnóstica
├── db.py              # fachada fina; delega ao dialeto
├── doctor.py          # checagens genéricas; probe de escrita delega
├── cli.py             # + --dialect
├── errors.py          # inalterado
├── observability.py   # inalterado
├── guardrails/
│   ├── sql.py         # validar(sql, dialeto, perfil)
│   ├── policy.py      # recebe o dialeto
│   └── ratelimit.py   # inalterado
└── dialetos/
    ├── base.py        # o Protocol
    ├── postgres.py
    ├── mysql.py
    └── sqlserver.py
```

O Protocol, com onze membros:

```python
class Dialeto(Protocol):
    nome: str                          # "postgres" | "mysql" | "sqlserver"
    sqlglot_dialeto: str               # "postgres" | "mysql" | "tsql"
    funcs_proibidas: frozenset[str]
    schema_padrao: str                 # "public" | <database> | "dbo"

    def criar_pool(self, s: Settings) -> PoolLike: ...
    def configurar(self, conn) -> None:      # como deixar a sessão read-only
    def resetar(self, conn) -> None:         # DISCARD ALL | RESET CONNECTION | (nada)
    def sql_introspecao(self, tipo, **kw) -> str
    def sql_amostra(self, tabela: str, n: int) -> str    # LIMIT n | TOP n
    def sql_probe_escrita(self) -> str
    erros_readonly: tuple[type[Exception], ...]          # o que conta como "escrita recusada"
```

`PoolLike` é o mínimo que `db.py` usa: um `.connection()` context manager e `.close()`.
`psycopg_pool` já tem essa forma; MySQL e SQL Server ganham wrappers finos sobre o pool
nativo de cada driver.

**Drivers como extras opcionais** — quem só usa Postgres não instala pymssql:

```toml
[project.optional-dependencies]
postgres  = ["psycopg[binary,pool]>=3.2"]
mysql     = ["mysql-connector-python>=9"]
sqlserver = ["pymssql>=2.3"]
```

`uv sync --extra mysql`. Cada módulo de dialeto importa o driver **lazy**, com erro legível
se o extra não foi instalado.

---

## 4. Os três cadeados por dialeto (a tabela honesta)

Esta é a seção que o README precisa refletir, não esconder.

| | PostgreSQL | MySQL | SQL Server |
|---|---|---|---|
| **Cadeado nº 1** | `default_transaction_read_only=on` **no role** + `GRANT SELECT` | `SET SESSION TRANSACTION READ ONLY` + `GRANT SELECT` | **só `GRANT`/`DENY`** (`db_datareader` + DENY explícito) |
| **Reset de sessão** | `DISCARD ALL` | `RESET CONNECTION` | **não existe equivalente** |
| **Timeout** | `statement_timeout` (servidor) | `max_execution_time` (só SELECT) | client-side (pymssql) |
| **Erro do probe** | `25006` / `42501` | `1792` / `1142` | `262` / `229` |
| **Força real** | cinto **e** suspensório | cinto fraco + suspensório | **só suspensório** |

O README hoje afirma *"o próprio Postgres recusa a escrita"*. **Essa frase fica falsa no SQL
Server**, onde não há read-only de sessão nem de transação: a garantia é inteiramente
permissão. Vender a mesma promessa nos três seria vender segurança que não entregamos.

**Entregável de documentação (não é nota de rodapé):** o README e o `docs/02-preparar-o-banco.md`
passam a ter a tabela acima, e o texto dos três cadeados vira por-dialeto.

**Gap conhecido — SQL Server sem reset de sessão.** Não há `DISCARD ALL`. O `sp_reset_connection`
é mecanismo de TDS usado pelo pooling do .NET, não algo que se chame de forma útil daqui.
Mitigação: o validador já barra `SET` (nó `Set` em `TAGS_PROIBIDAS`) e DDL, então temp tables e
mudança de SET options não passam pelo `consultar`. O que sobra é resíduo teórico, e vai
documentado como tal em vez de fingido resolvido.

---

## 5. O que muda no código existente

Três defeitos que só apareceriam em produção no SQL Server. Achados testando, não lendo.

**5.1 — `injetar_limit` tem o dialeto hardcoded.**
Hoje: `arvore.limit(teto).sql(dialect="postgres")`. Num SQL Server, `SELECT TOP 9999 * FROM t`
(acima do teto) seria reescrito como `SELECT * FROM t LIMIT 1000` → **erro de sintaxe**.
Correção: `injetar_limit(sql, teto, dialeto)`, emitindo no dialeto do alvo.

**5.2 — `amostra` monta `LIMIT` na mão e escapa da transpilação.**
`amostra` constrói `SELECT * FROM {tabela} LIMIT {n}`. O `injetar_limit` **devolve a string
intocada** quando `n ≤ teto` — decisão deliberada dele de não mexer em SQL que já respeita o
limite. Resultado: o `LIMIT` cru chega no SQL Server e explode. Não dá para confiar na
transpilação; por isso `sql_amostra(tabela, n)` é membro do `Dialeto`.

**5.3 — `_validar_ident` é regex de Postgres.**
`^[A-Za-z_][A-Za-z0-9_$]*$` rejeita `2fa_tokens` (legítimo no MySQL com crases) e **aprova**
`Order`, que é reservada no T-SQL e precisa virar `[Order]`. Correção: parar de validar-e-
interpolar e deixar o sqlglot citar (`identify=True` → `"t"` / `` `t` `` / `[t]`). Mais robusto
que a regex atual **até no Postgres**, e some com uma classe inteira de injeção nas ferramentas
de introspecção.

**5.4 — `FUNCS_PROIBIDAS` vira por dialeto.** O mecanismo (`exp.Anonymous` + nome) fica; muda a
lista. MySQL ganha `load_file`, `sleep`, `benchmark`, `sys_exec`, `sys_eval`. T-SQL ganha
`openquery`, `openrowset`, `opendatasource`, mais a família `xp_*`/`sp_oa*`.

---

## 6. Semântica divergente: no MySQL, `schema` **é** o database

MySQL não tem a camada schema separada — `information_schema.schemata` lista os **databases**
da instância. Isso colide com o não-objetivo "1 database por instância".

**Decisão:** no MySQL, `listar_schemas` devolve **apenas o database configurado**, nunca a
instância inteira. `listar_tabelas(schema)` trata `schema` como o database e **recusa** um
valor diferente do configurado.

Razão: devolver a instância inteira vazaria nomes de bancos vizinhos — metadado que o dialeto
Postgres não entrega hoje. Feature-parity aqui significaria piorar a segurança do MySQL para
imitar uma capacidade que o Postgres nem tem.

No SQL Server o problema não existe: schemas são reais (`dbo`), `information_schema` é por
database, e o mapeamento é próximo do Postgres.

---

## 7. Não-objetivos (atualizados)

- **Escrita no banco:** fora **deste spec** (era "nunca"). Terá spec próprio. O princípio do §1
  vale desde já: a config só subtrai, nunca soma.
- **SGBDs além de PostgreSQL, MySQL e SQL Server:** fora. O `Dialeto` não é um plugin público;
  é um contrato interno com três implementações.
- **Múltiplos databases numa mesma instância:** fora — e no MySQL isso vira ainda mais
  relevante (§6).
- **Consultas de negócio nomeadas:** fora (inalterado).
- **Paridade cega entre dialetos:** explicitamente fora. Onde o banco é mais fraco, o produto
  diz que é mais fraco (§4).

---

## 8. Fases

**Fase 0 — refatorar para multi-dialeto, só com Postgres.** Zero função nova.
Renomear o pacote (`pg_readonly_mcp` → `db_mcp`) e o comando (`pg-readonly-mcp` → `db-mcp`),
extrair o `Dialeto`, implementar `postgres.py`, corrigir 5.1–5.3, `--dialect` com default
`postgres`. Atualizar o remote e a pasta do clone local.
**Prova de que nada quebrou: os mesmos 119 testes verdes e o `doctor` 6/6 contra o container de
demo.** Sem esta fase, refatoração e MySQL entram juntos e não se sabe qual quebrou. É a fase
que dá vontade de pular e é exatamente a que protege o que já funciona.

**Fase 1 — MySQL.** `dialetos/mysql.py`, extra `mysql`, container de demo, `docs/`, CI.

**Fase 2 — SQL Server.** `dialetos/sqlserver.py`, extra `sqlserver`, demo, `docs/`, CI. É a
fase mais arriscada: driver menos convencional, sem reset de sessão, timeout client-side, e o
`OPENROWSET`/`OPENDATASOURCE` a fechar.

---

## 9. Testes e CI

**A suite de ataques já existe — o que falta é parametrizá-la por dialeto.**
`tests/test_sql.py::test_casos_adversariais_bloqueados` já cobre os 24 ataques do Postgres
(incluindo evasão por aspas, qualificação com `pg_catalog.`, `query_to_xml`, advisory lock,
`set_config`), e `tests/test_policy.py` já cobre os casos de sombreamento de CTE
(`test_cte_irmao_posterior_nao_sombreia_tabela_real`). O trabalho da Fase 0 **não** é escrever
essa suite: é **reestruturá-la para receber o dialeto**, de forma que Fases 1 e 2 só acrescentem
a sua tabela de ataques (MySQL: `load_file`, `sleep`, `benchmark`; T-SQL: `openquery`,
`openrowset`, `opendatasource`). É essa estrutura parametrizada que protege contra a divergência
que motivou a decisão 1.

**O que falta de verdade é teste de fiação (e2e).** Os testes acima exercitam
`validar_somente_leitura()` **isolado, sem banco**. O `test_e2e_integration.py` toca o caminho
completo, mas só com dois casos (um `SELECT 1` e um `DELETE`). Falta provar, contra o banco
vivo, que os guardrails estão **ligados** no caminho `Nucleo.consultar` → guardrails → pool →
banco — um validador correto que não foi plugado não protege ninguém. Isso vira
`tests/test_ataques_e2e.py`, parametrizado por dialeto, com um subconjunto representativo (não
a lista inteira: a cobertura da lista é dos testes unitários; aqui o alvo é a fiação).

**Regressão de parser:** os casos que hoje falham fechado por `ParseError` (`INTO OUTFILE`,
`WAITFOR DELAY`) ganham teste explícito. Se um upgrade do sqlglot passar a parseá-los, o teste
vermelho avisa antes de o buraco abrir em silêncio.

**Demo:** `docker-compose.yml` ganha profiles — `docker compose --profile mysql up -d`. Os três
containers sobem semeados com o mesmo schema lógico e o usuário read-only já criado, seguindo
o padrão de `demo/init/*.sql`.

**CI:** o job `integration` já roda Postgres como service e semeia com os `demo/init/*.sql`.
Replicar para `mysql:8` e `mcr.microsoft.com/mssql/server:2022`. O de SQL Server precisa de
`ACCEPT_EULA=Y` e ~2 GB de RAM — cabe no runner do GitHub, mas é o mais lento.

---

## 10. Riscos e pontos em aberto

| Risco | Impacto | Encaminhamento |
|---|---|---|
| `OPENDATASOURCE('X','Y')..t` parseia com raiz `Select` e sintaxe de 4 partes | bypass de allowlist no T-SQL | Verificar na Fase 2 se vira `exp.Anonymous` (o `OPENQUERY` vira). Se não virar, o bloqueio precisa de checagem estrutural, não de lista de nomes. |
| SQL Server sem reset de sessão | resíduo de estado entre clientes no pool | Documentar (§4). Mitigado pelo `Set`/DDL já barrados. |
| `sqlglot` passar a parsear `INTO OUTFILE`/`WAITFOR` | abre buraco em silêncio | Teste de regressão (§9). |
| Teto de `MAX_RESULT_BYTES` é pós-materialização | pico de memória com linha larga | Já é limitação conhecida e documentada do produto; não piora com multi-dialeto. Fora de escopo. |
| `pymssql` menos convencional que pyodbc | suporte/bugs | Aceito conscientemente (decisão 3). Se Entra ID virar requisito, reabrir com a opção `MSSQL_DRIVER`. |

---

## 11. Critério de pronto

- `db-mcp --dialect {postgres,mysql,sqlserver} doctor` fica verde contra os três containers de demo.
- A suite de ataques roda e barra tudo nos três dialetos.
- CI verde nos três, incluindo o job de integração.
- O README diz a verdade do §4 — a força de cada cadeado por dialeto, sem promessa uniforme.
