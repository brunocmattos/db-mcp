-- Cadeado nº 1 (no banco): o usuário que o MCP usa é read-only de verdade.
-- Mesmo desenho do deployment real, só que com senha de brincadeira.

CREATE ROLE mcp_ro LOGIN PASSWORD 'mcp_ro_demo'
    CONNECTION LIMIT 5;

-- Toda transação da conexão nasce READ ONLY — o próprio Postgres recusa escrita.
ALTER ROLE mcp_ro SET default_transaction_read_only = on;

-- Corta consultas que passem de 5s.
ALTER ROLE mcp_ro SET statement_timeout = '5s';

-- Só pode ler: CONNECT + USAGE + SELECT, nada de INSERT/UPDATE/DDL.
GRANT CONNECT ON DATABASE demo TO mcp_ro;
GRANT USAGE ON SCHEMA public TO mcp_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO mcp_ro;

-- Se novas tabelas surgirem no schema, o mcp_ro já ganha SELECT nelas.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO mcp_ro;
