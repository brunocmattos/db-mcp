-- Cadeado nº 1 (no banco): o usuário que o MCP usa é read-only de verdade.
-- Mesmo desenho do deployment real, só que com senha de brincadeira.
--
-- ⚠️ ASSIMETRIA COM O POSTGRES — leia antes de copiar isto pra produção:
-- o Postgres tem `ALTER ROLE ... SET default_transaction_read_only = on`, que faz
-- TODA transação daquele usuário nascer read-only, venha de onde vier. **O MySQL não
-- tem equivalente por usuário.** Aqui o cadeado é só o GRANT: sem INSERT/UPDATE/DELETE
-- /CREATE concedidos, o servidor recusa a escrita com o erro 1142.
-- O `SET SESSION TRANSACTION READ ONLY` (o "cinto" que no Postgres vem do role) só
-- existe se a APLICAÇÃO o aplicar — e por isso o dialeto MySQL precisa reaplicá-lo a
-- cada checkout do pool. Se ele esquecer, o GRANT ainda segura; é por isso que o
-- GRANT abaixo é o que não pode faltar.

CREATE USER 'mcp_ro'@'%' IDENTIFIED BY 'mcp_ro_demo'
    WITH MAX_USER_CONNECTIONS 5;

-- Só pode ler: SELECT no database da demo, nada de INSERT/UPDATE/DDL.
-- `demo.*` já cobre as tabelas que surgirem depois (equivale ao ALTER DEFAULT
-- PRIVILEGES do Postgres).
GRANT SELECT ON demo.* TO 'mcp_ro'@'%';

FLUSH PRIVILEGES;
