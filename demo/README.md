# Demo

Postgres descartável pra experimentar o MCP sem apontar pro seu banco. Veja a
seção "Experimente em 30 segundos" no [README principal](../README.md).

Os arquivos em `init/` rodam uma vez, na primeira subida do container (o Postgres
executa tudo que estiver em `/docker-entrypoint-initdb.d`, em ordem):

| Arquivo | O que faz |
|---|---|
| `01-schema.sql` | cria `clientes`, `pedidos`, `usuarios` e uma view |
| `02-seed.sql` | insere dados fictícios |
| `03-mcp-ro.sql` | cria o usuário read-only `mcp_ro` (só `SELECT`, transação read-only, timeout) |

As credenciais (em `../.env.demo`) são de brincadeira — versionadas de propósito.
Para recomeçar do zero: `docker compose down -v && docker compose up -d`.
