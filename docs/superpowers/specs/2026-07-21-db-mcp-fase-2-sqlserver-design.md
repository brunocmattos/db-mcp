# Fase 2 — dialeto SQL Server (design)

**Data:** 2026-07-21 · **Estado:** aprovado, aguardando plano de implementação
**Antecessores:** [spec multi-dialeto](2026-07-16-db-mcp-multi-dialeto-design.md) ·
[plano Fase 0](../plans/2026-07-16-db-mcp-fase-0-multi-dialeto.md) ·
[plano Fase 1](../plans/2026-07-20-db-mcp-fase-1-mysql.md)

> **Tudo neste documento marcado 📏 foi MEDIDO** contra um SQL Server 2022 real
> (`mcr.microsoft.com/mssql/server:2022-latest`, container descartável na porta 1434) ou
> contra o sqlglot 30.12.0 instalado. O que não está marcado é decisão de desenho, não fato.
> Esta separação é deliberada: a Fase 1 provou que os defeitos caros aparecem exatamente onde
> se presumiu em vez de medir.

## 1. Objetivo e não-objetivos

**Objetivo:** o db-mcp falar com um terceiro banco. `db-mcp --dialect sqlserver doctor`
fechando 6/6 contra um SQL Server real, com a suíte verde nos três bancos.

**Não-objetivos**, herdados do spec multi-dialeto §1: escrita (spec próprio), Entra ID,
Always Encrypted — os dois últimos são o custo aceito da escolha do pymssql.

**Explicitamente fora desta fase:** a correção do colapso do `catalog` na allowlist. Foi
encontrada durante o design desta fase e **entregue antes dela**, sozinha, em `26f2bff` —
ver §7.

## 2. O que muda

```
+ src/db_mcp/dialetos/sqlserver.py     novo
~ src/db_mcp/dialetos/__init__.py      uma linha no _REGISTRO
~ pyproject.toml                       extra opcional: sqlserver = ["pymssql>=2.3"]
+ tests/test_sql_sqlserver.py          corpus de ataque
+ demo/init-sqlserver/*.sql            schema, seed, usuário read-only
~ docker-compose.yml                   profile sqlserver
~ .github/workflows/ci.yml             job integration-sqlserver
~ docs/                                tabela dos cadeados + receita de DENY
```

**Nenhum arquivo do núcleo muda.** O único caso que exigiria (`guardrails/policy.py`) foi
extraído para fora da fase de propósito, para que o padrão "um dialeto = um arquivo + uma
linha" continue sendo verdade medível e não slogan.

### 🪤 O gotcha nº 1, que mata em silêncio

`nome = "sqlserver"` mas **`sqlglot_dialeto = "tsql"`**. No `postgres.py` e no `mysql.py` os
dois coincidem *por acaso*; quem copiar o padrão leva `ValueError` em toda query — e uma
recusa que não é `McpDbError` **escapa da auditoria**. Já guardado por
`test_invariante_todo_dialeto`, que enumera o `_REGISTRO`.

## 3. Conexão: sem pool

📏 **O pymssql 2.3.13 não tem pool nem reset de sessão.** Medido: nenhum símbolo com "pool"
no módulo, e `Connection` expõe apenas `arraysize, as_dict, autocommit, autocommit_state,
bulk_copy, close, commit, cursor, rollback`.

Isso **contradiz uma premissa escrita do spec anterior** (§"PoolLike", linha 124): *"MySQL e
SQL Server ganham wrappers finos sobre o pool nativo de cada driver"*. Para o SQL Server, esse
pool nativo não existe. A decisão nº 3 daquele spec pesou apenas `msodbcsql18` contra "sem
Entra ID / Always Encrypted" — a ausência de pool nunca entrou na conta. Pelo critério que
**reprovou o PyMySQL** na decisão nº 4 ("pool nativo **e** reset"), o pymssql também seria
reprovado.

**Decisão: `criar_pool` devolve um `_ConexaoPorConsulta`** — satisfaz `PoolLike` abrindo uma
conexão nova a cada `.connection()`; `.close()` é no-op.

📏 **Custo medido:** conexão nova + query = **15,61 ms** (mediana, n=15); conexão reusada =
**1,28 ms**. Handshake ≈ **14,3 ms** por consulta.

**Por que aceitar 14,3 ms:**
1. É ~1% do round-trip que o usuário percebe (uma consulta via MCP custa centenas de ms a
   segundos, dominada pelo modelo).
2. **Elimina por construção** a classe de bug que quase abriu o cadeado na Fase 1: sem reuso,
   não há estado de sessão a vazar. O `pool_reset_session=True` zerando o read-only não tem
   análogo possível aqui.
3. **Resolve de graça o gap conhecido** que o spec anterior encaminhou como "resíduo teórico
   documentado": o SQL Server não tem `DISCARD ALL`/`RESET CONNECTION` — mas uma conexão nova
   **é** o reset.

**Custo honesto, registrado:** sob carga alta e concorrente, abrir conexão por query pressiona
o servidor. Não é o perfil deste produto (somente leitura, com rate limit), mas é a razão pela
qual esta decisão deve ser revisitada se o perfil mudar.

**Alternativas descartadas:** pool escrito à mão (escreveria justamente a peça que falhou
aberta e em silêncio no MySQL, para economizar 14 ms); trocar para pyodbc (pooling do
gerenciador ODBC, mas reabre a decisão travada e exige `msodbcsql18` no SO, no CI e em quem
instalar — quebra o "clona e roda" de um produto público).

## 4. O cadeado read-only — e o falso positivo a evitar

📏 **Não existe cadeado de sessão no SQL Server.** `SET TRANSACTION READ ONLY` →
**erro 156, sintaxe inválida**. Não há `default_transaction_read_only` nem equivalente. A
proteção é **só GRANT/DENY**, e o `doctor` é a única verificação em tempo de configuração.

📏 **Erros da recusa de escrita**, com um `mcp_ro` real (GRANT SELECT em uma tabela):

| Tentativa | Erro |
|---|---|
| `INSERT INTO dbo.clientes` | **229** — `The INSERT permission was denied on the object` |
| `CREATE TABLE dbo._probe` | **262** — `CREATE TABLE permission denied in database` |

O spec anterior previu `262`/`229` e **acertou**.

### ⚠️ `erro_readonly` NÃO pode casar 229

O `229` é `permission denied on the object` — genérico. **Ele também é levantado quando falta
permissão de `SELECT`.** Se `erro_readonly` casasse `229`, uma conexão que falhou por motivo
não relacionado seria classificada como "somente-leitura confirmado": o falso positivo
perigoso que o docstring de `erro_readonly` (`dialetos/base.py`) existe para alertar, no
cadeado que aqui **já é o único**.

**Decisão:** `sql_probe_escrita()` = `CREATE TABLE`, e `erro_readonly` casa **`262`** (e
`3906`, banco inteiro read-only). **Nunca `229`.** Isto espelha o raciocínio do MySQL, onde
`1792`/`1142` exigiram predicado em vez de tupla de classes.

## 5. Guardrails do T-SQL

📏 Medido com o pipeline real de `guardrails/sql.py` (parse `tsql`, `error_level=RAISE`,
`TAGS_PROIBIDAS`, `Anonymous`/`funcs_proibidas`):

| Ataque | Chega como | Quem barra |
|---|---|---|
| `OPENQUERY(...)` | `exp.Anonymous` | **`funcs_proibidas`** |
| `OPENDATASOURCE(...)` | `exp.Anonymous` | **`funcs_proibidas`** |
| `xp_cmdshell(...)`, `fn_get_audit_file`, `fn_trace_gettable` | `exp.Anonymous` | **`funcs_proibidas`** |
| `[xp_cmdshell](...)` e `"xp_cmdshell"(...)` | `.name` normaliza a citação | **`funcs_proibidas`** |
| `EXEC` / `sp_executesql` | raiz `Execute` / `ExecuteSql` | raiz não é `Select` |
| `INSERT` | raiz `Insert` | raiz não é `Select` |
| `SELECT ... INTO` | tag `Into` | `TAGS_PROIBIDAS` |
| `OPENROWSET`, `OPENROWSET BULK` | — | **só `ParseError`** ⚠️ |
| `WAITFOR DELAY` | — | **só `ParseError`** ⚠️ |
| `EXECUTE AS LOGIN` | — | **só `ParseError`** ⚠️ |
| `GO` (batch) | — | **só `ParseError`** ⚠️ |

Isso **corrige uma expectativa do `CLAUDE.md`**, que registrava `OPENQUERY`/`OPENROWSET`/
`OPENDATASOURCE` como "passam pelo validador com raiz `Select`". Passam pela checagem de raiz,
sim — mas dois dos três caem na blocklist de funções. O mecanismo já existe; basta popular a
lista.

**`funcs_proibidas` (lista fechada, não "a família `xp_*`").** A lista é enumerada de propósito:
um prefixo `xp_*` genérico daria falsa sensação de cobertura (as `fn_*` ficariam de fora) e
barraria nomes de usuário que por acaso comecem com `xp_`.
⚠️ Lista vazia falharia **aberta** — já guardado por `test_invariante_todo_dialeto`.

📏 **Correção pós-revisão (2026-07-21): a lista tem dois grupos com forças MUITO diferentes, e
a primeira redação deste spec não distinguia.**

*Grupo A — a blocklist é mesmo quem barra.* `openquery`, `opendatasource`, `openrowset`,
`fn_get_audit_file`, `fn_trace_gettable`, `fn_my_permissions`, `fn_dblog`, `fn_dump_dblog`.
Executam de fato como função/rowset dentro de um `SELECT`, chegam como `exp.Anonymous` e
passam a checagem de raiz. Sem a lista, passariam.

*Grupo B — redundância deliberada, NÃO a defesa real.* `xp_cmdshell`, `xp_regread`,
`xp_regwrite`, `xp_dirtree`, `xp_fileexist`, `xp_subdirs`, `xp_msver`. São **stored procedures
estendidas**: só invocáveis por `EXEC`, nunca como função num `SELECT`. Medido contra SQL Server
2022 **como `sa`** (para eliminar o GRANT como variável):

```
SELECT * FROM xp_cmdshell('dir')  ->  Msg 208: Invalid object name 'xp_cmdshell'.
SELECT xp_cmdshell('dir')         ->  Msg 195: 'xp_cmdshell' is not a recognized built-in function name.
```

O motor recusa a sintaxe para **qualquer** usuário. A forma real de ataque (`EXEC xp_cmdshell
'dir'`) morre na checagem de raiz, independente da blocklist. Elas ficam na lista porque
sobra-defesa é barata e errar pra menos é caro — mas **afirmar que "só a blocklist as pega"
seria falso**, e este spec afirmava.

⚠️ Consequência prática para quem mantiver a lista: apagar uma entrada do **grupo A** abre um
buraco real; apagar uma do **grupo B** não muda nada. O corpus de ataque tem que exercitar o
grupo A pelo caminho que chega na blocklist — inclusive a forma de 3 argumentos do `OPENROWSET`,
que parseia (a de credencial `;`-separada e a `BULK` morrem antes, no `ParseError`).

**Os quatro ⚠️ falham fechado por acidente**, não por desenho — exatamente o caso do
`INTO OUTFILE` no MySQL. Ganham regressão em `tests/test_sql_sqlserver.py` que exige
**recusa** (`McpDbError`), **não** o mecanismo: se o sqlglot passar a parseá-los, o teste
avisa em vez de o buraco abrir calado.

### 🪤 Aspas duplas são citação, não string

📏 No T-SQL `"xp_cmdshell"(...)` é um identificador citado e `.name` devolve `xp_cmdshell` —
**o oposto do MySQL**, onde aspas duplas são STRING e a citação é a crase. Consequência
prática para quem escrever o corpus: **o caso do Postgres porta para cá; o do MySQL não.**

## 6. Introspecção, identidade e limites

- `schema_padrao = "dbo"` — constante, como no Postgres (≠ MySQL, onde é o database).
- `INFORMATION_SCHEMA` existe no SQL Server; a introspecção segue o padrão dos outros dois,
  com o identificador por query parameter, fora do validador.
- 📏 `sql_identidade()` = `SELECT SUSER_SNAME() AS usuario, DB_NAME() AS banco` — testado,
  devolve `('sa', 'master')`. Os apelidos `usuario`/`banco` são obrigatórios (o doctor lê por
  essas chaves).
- `porta_padrao = 1433` (o demo mapeia `1434:1433` no host, porque 1433 costuma estar
  ocupada por instância local).
- **`injetar_limit` já funciona**: emite `TOP` no tsql, com teste desde a Fase 0
  (`test_injetar_limit_tsql_sem_limite_usa_top`). **Nada a fazer.**
- Timeout: client-side, via parâmetros do pymssql (`timeout`, `login_timeout`) — não há
  `statement_timeout` de servidor como no Postgres.

## 7. O que esta fase NÃO precisa fazer (e por quê)

📏 Durante o design mediu-se que `guardrails/policy.py` **descartava o `catalog`** ao montar o
nome da tabela: `outrodb.dbo.clientes` era vista como `dbo.clientes` e casava com a entrada de
allowlist feita para o banco corrente.

Demonstrado contra o SQL Server real: com `mcp_ro` tendo GRANT em `demo.dbo.clientes` **e** em
`financeiro.dbo.clientes` (arranjo comum — cópias dev/homolog/prod, multi-tenant), allowlist
`['dbo.clientes']`, o servidor entregou `financeiro.dbo.clientes` → `DADO CONFIDENCIAL`, e a
allowlist antiga **deixava passar**.

Corrigido **antes** desta fase, sozinho, em `26f2bff`: qualquer referência que nomeie um
catalog é recusada, inclusive com `allowlist=["*"]` (o `*` desliga a allowlist, não o
invariante). Este foi **o primeiro caso em que um dialeto novo exigiu mexer no núcleo** — o
padrão "um arquivo + uma linha" vale para o dialeto, não para os cadeados compartilhados.

### 🚨 Metadado vaza por padrão — vira receita de deployment

📏 Um login com `GRANT SELECT` em **uma** tabela ainda enxerga, sem grant extra: a lista de
**todos os bancos** (`sys.databases`, 6 linhas), **todos os logins SQL** (`sys.sql_logins`) e o
**catálogo do `master`** (`master.sys.objects`). Não é dado de usuário — dado de outro banco é
recusado com **916** enquanto o login não tiver acesso lá —, mas é reconhecimento de terreno
de graça, **sem equivalente no Postgres/MySQL**.

📏 Medido que fecha: `DENY VIEW ANY DATABASE` · `DENY VIEW ANY DEFINITION` ·
`REVOKE CONNECT FROM guest` nos demais bancos. Resultado: `master.sys.objects` cai de 3 para
**0** linhas e `sys.databases` de 6 para **3** (`master`/`tempdb`/o próprio — piso do produto,
não dá para zerar).

Isso vira **instrução** em `docs/02-preparar-o-banco.md` e no seed do demo, não nota de rodapé.

## 8. Demo e CI

`docker compose --profile sqlserver`, porta **1434** (1433 costuma estar ocupada por instância
local), espelhando o padrão dos outros dois demos: schema, seed e `mcp_ro` versionados em
`demo/init-sqlserver/`, com os `DENY` do §7 aplicados no `03-mcp-ro.sql`.

📏 **Custo real do container**, medido — o número "2,34 GB" citado no brainstorm era o tamanho
em disco, não o que o CI paga:

| Imagem | Em disco | **Download (comprimido)** | Boot até aceitar conexão | RAM |
|---|---|---|---|---|
| `postgres:17-alpine` | 424 MB | 112 MB | ~1 s | — |
| `mysql:8.4` | 1,13 GB | 231 MB | ~10 s | — |
| `mssql/server:2022` | 2,34 GB | **596 MB** | **5,6 s** | **1,07 GB** |

É a mais pesada das três (+365 MB de download contra o MySQL), mas o boot é **mais rápido que
o do MySQL**, a RAM cabe folgada nos 7,4 GB do runner, e **Actions é gratuito para repositório
público**. **Conclusão: o job de integração entra no CI**, como os outros dois. O custo é
menos de um minuto de espera, não dinheiro.

⚠️ O CI **precisa** de `--all-extras` (já é assim desde a Fase 1): sem o driver, o mypy não
resolve o import **e** o `test_invariante_todo_dialeto[sqlserver]` se pula, silenciando o gate
justamente onde ele mais importa.

## 9. Definição de pronto

1. `db-mcp --dialect sqlserver doctor` fecha **6/6** contra o container real.
2. Suíte verde nos **três** bancos, com os skips auditados (`-rs`) — o corpus de ataque dos
   outros dialetos deve se pular, e a união dos três modos cobre o total.
3. `test_invariante_todo_dialeto[sqlserver]` passando (pega `tsql`≠`sqlserver` e
   `funcs_proibidas` vazia).
4. Regressão exigindo **recusa** para `OPENROWSET`, `WAITFOR DELAY`, `EXECUTE AS` e `GO`.
5. Regressão exigindo que `erro_readonly` **não** case `229`.
6. `ruff` · `ruff format` · `mypy src` limpos.
7. CI verde com os **três** jobs de integração.
8. Tabela dos cadeados com a coluna do SQL Server preenchida com o que foi medido, incluindo
   "não existe cadeado de sessão" e o vazamento de metadado — sem maquiagem.

## 10. Riscos

| Risco | Impacto | Encaminhamento |
|---|---|---|
| Conexão por consulta sob concorrência | pressão no servidor | Registrado em §3. Revisitar se o perfil deixar de ser read-only com rate limit. |
| `erro_readonly` casar `229` por descuido | doctor confirma read-only para conexão que não é | Regressão explícita (§9.5) + o porquê no docstring. |
| sqlglot passar a parsear `OPENROWSET`/`WAITFOR` | buraco abre calado | Testes exigem **recusa**, não mecanismo (§5). |
| Operador não aplicar os `DENY` | metadado da instância exposto ao agente | Instrução na doc e no seed do demo (§7), não nota de rodapé. |
| Imagem de 596 MB no CI | ~1 min a mais por run | Aceito e medido (§8). Actions é gratuito para repo público. |
