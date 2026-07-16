# Troubleshooting

## Lendo o doctor

Cada `[X]` já vem com uma linha `↳` de remediação. Resumo:

| Checagem falha | Causa provável | O que fazer |
|---|---|---|
| Config inválida / não carregou | falta `PG_HOST`/`PG_DBNAME`/`PG_PASSWORD` no `.env` | preencha o `.env` (veja `.env.example`); cheque `--env`/`--config`. |
| TCP inacessível | rede/VPN/firewall/`pg_hba` | ligue a VPN; teste `nc -vz SEU_HOST SUA_PORTA`; confira a linha do `mcp_ro` no `pg_hba.conf`. |
| Falha de autenticação | senha errada ou `pg_hba` não libera | confira `PG_PASSWORD`/`PG_SSLMODE`; ajuste `pg_hba.conf` e `SELECT pg_reload_conf();`. |
| NÃO é somente-leitura | o `mcp_ro` consegue escrever (falha de segurança) | `REVOKE ALL` e conceda só `SELECT`; veja [`02-preparar-o-banco.md`](02-preparar-o-banco.md). |
| Tabelas da allowlist ausentes | nome errado ou sem `GRANT` | corrija `schema.tabela` na `allowlist`, ou o `GRANT SELECT` do `mcp_ro`. |
| Latência crítica | rota de rede/VPN ruim | verifique a VPN; acima de 250ms vira só aviso, e a checagem só falha passando de 2s. |

## Instalação (uv / Python)

Requer Python 3.11+. O dev trabalha no 3.12 (fixado no `.python-version`) e o CI roda em
3.12 e 3.13.

- Se o `uv` reclamar da versão do Python, force com `uv sync --python 3.12`. Testado até 3.13.
- Erro de wheel ou compilação no Windows quase sempre é a versão do interpretador: o
  `sqlglot` é puro-Python e não compila. Confirme que está no 3.12.
- `uv sync --locked` falhando no CI quer dizer `uv.lock` desatualizado. Rode `uv lock` e comite.

## Cliente MCP não enxerga o servidor

- Claude Desktop: feche e reabra por completo, ele só lê a config na inicialização. Um JSON
  malformado desativa todos os servidores de uma vez, então valide as vírgulas e chaves. Logs em
  `%APPDATA%\Claude\logs\mcp-server-db-mcp.log` (Windows) ou `~/Library/Logs/Claude/` (macOS).
- Claude Code: `claude mcp list` e `claude mcp get db-mcp`. Servidores de escopo `project`
  (`.mcp.json`) pedem aprovação uma vez; resete com `claude mcp reset-project-choices`.
- `command not found: uv`: o cliente não herdou o PATH. Use o caminho absoluto do `uv` no
  `command` (descubra com `where uv` ou `which uv`).

## Erros que o agente pode ver (via `amostra` / `consultar`)

Códigos estáveis: `sql_invalido`, `somente_leitura`, `fora_da_allowlist`, `limite_de_taxa`,
`resultado_grande_demais`, `timeout`, `erro_banco`. Significam, respectivamente: SQL não é um
`SELECT` válido; tentou escrever; tabela fora da allowlist; excedeu o rate limit; resultado
acima do teto de bytes; query passou do `statement_timeout`; erro do próprio PostgreSQL (tabela
ou coluna inexistente, etc.). As ferramentas `amostra` e `consultar` devolvem esse código num
objeto `{"erro", "detalhe"}`; a introspecção propaga o erro.

Falha de token no transporte HTTP não aparece aqui: o FastMCP responde `401` antes da
ferramenta rodar, então o cliente vê um erro de conexão, não um `{"erro": ...}`.
