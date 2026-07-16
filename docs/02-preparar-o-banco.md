# 02: Preparar o banco (usuário read-only + rede)

Troque `SEU_BANCO`, `SUA_SENHA`, `SEU_IP` pelos seus valores e rode os comandos SQL como
um usuário administrativo (ex.: `postgres`). Isto monta os dois primeiros cadeados descritos
no README: o usuário só-leitura no banco e a liberação de rede. Fazer isto é pré-requisito
pra rodar o `doctor` (sem ele, as checagens de auth e de read-only falham).

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

## Validar tudo de uma vez

Da máquina que vai rodar o MCP (com a rede/VPN ativa):

```bash
uv run db-mcp doctor
```

As 6 checagens devem passar. Se "TCP inacessível", olhe a rede e o `pg_hba`. Se "Falha de
autenticação", olhe a senha e o `pg_hba`. Se "NÃO é somente-leitura", revise os GRANTs acima.
