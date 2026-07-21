-- Cadeado no 1 (no banco): o usuario que o MCP usa e read-only de verdade.
-- Credenciais FAKE e publicas, parte do exemplo. Nao sao segredo.
--
-- ATENCAO: os DENY abaixo nao sao enfeite. MEDIDO no SQL Server 2022: sem eles, um
-- login com GRANT SELECT em UMA tabela ainda enxerga a lista de TODOS os bancos da
-- instancia (sys.databases), TODOS os logins SQL (sys.sql_logins) e o catalogo do
-- master (master.sys.objects). Nao e dado de usuario -- dado de outro banco e
-- recusado com erro 916 enquanto o login nao tiver acesso la --, mas e reconhecimento
-- de terreno de graca, e NAO tem equivalente no Postgres/MySQL.
--
-- Numeros medidos abaixo no Step 9 da T6 (ver docs/... e o relato da task).
USE master;
GO
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = 'mcp_ro')
    CREATE LOGIN mcp_ro WITH PASSWORD = 'Mcp_ro_demo_2026!', CHECK_POLICY = OFF;
GO
DENY VIEW ANY DATABASE TO mcp_ro;
DENY VIEW ANY DEFINITION TO mcp_ro;
GO

USE demo;
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'mcp_ro')
    CREATE USER mcp_ro FOR LOGIN mcp_ro;
GO
-- So SELECT, tabela a tabela. Nenhum db_datareader amplo.
GRANT SELECT ON dbo.clientes TO mcp_ro;
GRANT SELECT ON dbo.pedidos  TO mcp_ro;
GRANT SELECT ON dbo.usuarios TO mcp_ro;
-- A view tambem precisa do GRANT: com VIEW ANY DEFINITION negado, so aparece em
-- information_schema.views (usado por sql_introspecao) o objeto em que o login tem
-- alguma permissao propria.
GRANT SELECT ON dbo.pedidos_por_cliente TO mcp_ro;
GO
