# 02: Preparar o banco (usuário read-only + rede)

Troque `SEU_BANCO`, `SUA_SENHA`, `SEU_IP` pelos seus valores e rode os comandos SQL como
um usuário administrativo. Isto monta os dois primeiros cadeados descritos no README: o
usuário só-leitura no banco e a liberação de rede. Fazer isto é pré-requisito pra rodar o
`doctor` (sem ele, as checagens de auth e de read-only falham).

> ## ⚠️ Leia isto antes de escolher o quanto restringir
>
> Os dois cadeados **não têm a mesma força nos dois bancos**, e a diferença muda o que você
> precisa fazer aqui:
>
> | | PostgreSQL | MySQL |
> |---|---|---|
> | Permissão | `GRANT SELECT` | `GRANT SELECT` |
> | Transação read-only | `default_transaction_read_only` **no usuário** | só `SET SESSION TRANSACTION READ ONLY`, **por conexão** |
> | Quem garante | o **servidor** | a **aplicação** (o db-mcp reaplica a cada conexão do pool) |
>
> No PostgreSQL, mesmo com um bug no db-mcp, o servidor recusa a escrita — a trava está
> gravada no usuário. **No MySQL não existe equivalente por usuário.** Lá, o `GRANT` é o
> que de fato segura.
>
> 👉 **Consequência prática: no MySQL, conceder `SELECT` só nas tabelas certas não é
> "capricho de quem quer isolamento forte" — é a proteção principal.**

---

# PostgreSQL

## Cadeado nº 1: usuário só-leitura no banco

```sql
-- 1. cria o papel de login, sem privilégios de escrita
CREATE ROLE mcp_ro LOGIN PASSWORD 'SUA_SENHA'
  CONNECTION LIMIT 5;

-- 2. toda transação do papel já vem READ ONLY (o Postgres recusa escrita)
ALTER ROLE mcp_ro SET default_transaction_read_only = on;

-- 3. mata query/idle longos (defesa contra travar o banco)
ALTER ROLE mcp_ro SET statement_timeout = '5s';
ALTER ROLE mcp_ro SET idle_in_transaction_session_timeout = '10s';

-- 4. pode conectar no banco alvo
GRANT CONNECT ON DATABASE SEU_BANCO TO mcp_ro;
```

Agora conceda leitura nos schemas desejados (repita por schema; exemplo com `public`):

```sql
\c SEU_BANCO

GRANT USAGE ON SCHEMA public TO mcp_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO mcp_ro;

-- vale também para tabelas criadas no FUTURO
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO mcp_ro;
```

> **Quer isolamento forte de verdade?** O `GRANT SELECT` amplo acima é o modo cômodo, e aí a
> allowlist da aplicação (config) é quem restringe as tabelas — o que é defesa em profundidade,
> não um muro. Contra um cliente mal-intencionado, o limite que não se fura é o do **banco**:
> conceda `SELECT` só nas tabelas/views que o agente deve ver e nada mais —
>
> ```sql
> -- em vez do GRANT ... ON ALL TABLES:
> GRANT SELECT ON public.clientes, public.pedidos TO mcp_ro;
> ```
>
> Assim o próprio PostgreSQL recusa qualquer outra tabela, por mais esperto que seja o SQL. O
> `mcp_ro` não é superuser, então já não roda funções privilegiadas; se quiser fechar mais,
> `REVOKE EXECUTE` nas funções que você não quer expor.

Confirme que não há escrita (deve dar erro de permissão):

```sql
SET ROLE mcp_ro;
CREATE TABLE _teste_escrita (n int);   -- ERRO esperado: permission denied
RESET ROLE;
```

O `doctor` faz essa mesma prova sozinho, na checagem "Somente-leitura confirmado".

## Cadeado nº 2: liberar a rede (`pg_hba.conf`)

Libere o `mcp_ro` só das faixas de IP conhecidas (máquina de dev, servidor do MCP). No
`pg_hba.conf` do servidor, adicione uma linha por origem:

```
# TYPE  DATABASE   USER     ADDRESS         METHOD
host    SEU_BANCO  mcp_ro   SEU_IP/32       scram-sha-256
```

Recarregue sem reiniciar:

```sql
SELECT pg_reload_conf();
```

ou `sudo systemctl reload postgresql`.

---

# MySQL

Requer o extra do driver: `uv sync --extra mysql`, e `DIALETO=mysql` na config.

## Cadeado nº 1: usuário só-leitura no banco

```sql
-- 1. cria o usuário. O host ('%' = qualquer origem) É PARTE DA IDENTIDADE no MySQL:
--    restringi-lo já é metade do cadeado nº 2. Prefira o IP de quem roda o MCP.
CREATE USER 'mcp_ro'@'SEU_IP' IDENTIFIED BY 'SUA_SENHA'
  WITH MAX_USER_CONNECTIONS 5;

-- 2. só pode ler. `SEU_BANCO.*` já cobre as tabelas que surgirem depois
--    (equivale ao ALTER DEFAULT PRIVILEGES do Postgres).
GRANT SELECT ON SEU_BANCO.* TO 'mcp_ro'@'SEU_IP';

FLUSH PRIVILEGES;
```

> **⚠️ Não há passo 2 equivalente ao `default_transaction_read_only`.** O MySQL não permite
> gravar "esta sessão nasce read-only" no usuário. O db-mcp aplica
> `SET SESSION TRANSACTION READ ONLY` **a cada conexão** que pega do pool (o reset do pool
> apaga a configuração, então aplicá-la uma vez só falharia *aberto*) — mas isso é código
> nosso, não garantia do servidor.
>
> **Por isso, aqui, o `GRANT` restrito é o que realmente protege:**
>
> ```sql
> -- em vez do GRANT ... ON SEU_BANCO.*:
> GRANT SELECT ON SEU_BANCO.clientes TO 'mcp_ro'@'SEU_IP';
> GRANT SELECT ON SEU_BANCO.pedidos  TO 'mcp_ro'@'SEU_IP';
> ```
>
> **Nunca conceda `FILE`** ao `mcp_ro`: é o privilégio que habilita
> `SELECT ... INTO OUTFILE` (escreve arquivo no servidor) e `load_file()` (lê arquivo do
> servidor). O validador do db-mcp barra os dois, mas o cadeado nº 1 não deve depender disso.

Confirme que não há escrita (deve dar erro 1142):

```sql
-- conectado COMO mcp_ro:
CREATE TABLE _teste_escrita (n int);   -- ERRO esperado: 1142 command denied
```

O `doctor` faz essa mesma prova sozinho, na checagem "Somente-leitura confirmado" — e
repare que no MySQL ela reporta `42000` (privilégio), não `25006` (transação read-only)
como no Postgres. É a tabela do topo aparecendo na saída.

## Cadeado nº 2: liberar a rede

O MySQL não tem um `pg_hba.conf`. O controle de origem vem de duas partes:

1. **O host no próprio usuário** (acima): `'mcp_ro'@'10.0.0.5'` só autentica vindo daquele
   endereço. `'mcp_ro'@'%'` aceita de qualquer lugar — evite fora de demo.
2. **Firewall / security group** na porta 3306, porque o `bind-address` do servidor
   (`/etc/mysql/my.cnf`) costuma ser `0.0.0.0` quando o acesso remoto está ligado.

Exija TLS se o tráfego sai da máquina:

```sql
ALTER USER 'mcp_ro'@'SEU_IP' REQUIRE SSL;
```

---

## Validar tudo de uma vez

Da máquina que vai rodar o MCP (com a rede/VPN ativa):

```bash
uv run db-mcp doctor
```

As 6 checagens devem passar. Se "TCP inacessível", olhe a rede e o firewall. Se "Falha de
autenticação", olhe a senha e a regra de origem (`pg_hba.conf` no Postgres; o host do
usuário no MySQL). Se "NÃO é somente-leitura", revise os GRANTs acima — e note que essa
checagem prova o cadeado **do banco**, não o do db-mcp: ela conecta sem aplicar nenhuma
trava da aplicação, justamente pra medir o que o servidor recusa sozinho.
