# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e o projeto segue [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [0.2.0] - 2026-07-10

Primeira versão pública. Servidor MCP somente-leitura para qualquer PostgreSQL.

### Recursos

- **Seis ferramentas MCP:** introspecção de schemas, tabelas e views, `descrever_tabela`,
  `amostra` e `consultar` (um `SELECT` livre, validado — desligável com `ALLOW_FREEFORM_SQL=false`).
- **Três camadas de defesa:** usuário read-only no banco (`GRANT SELECT` +
  `default_transaction_read_only`), `pg_hba` por IP, e o validador de aplicação — só `SELECT`,
  instrução única, sem funções perigosas, com allowlist de tabelas, `LIMIT` automático, tetos de
  linhas e bytes, rate limit e, no transporte HTTP, autenticação Bearer com _fail-closed_.
- **Transportes stdio e HTTP.** O modo HTTP exige `AUTH_TOKEN` e recusa subir sem ele.
- **Comando `doctor`** com seis checagens de preflight (config, TCP, autenticação, read-only,
  allowlist e latência).
- **Trilha de auditoria:** uma linha por consulta, incluindo as recusadas.
- **Instalação assistida:** `SETUP.md` e uma skill do Claude Code que pergunta os parâmetros,
  ajuda a criar o usuário read-only, preenche a config e registra o MCP no cliente.
- **Demonstração em Docker:** um Postgres semeado com o usuário read-only pronto, para
  experimentar em 30 segundos sem um banco próprio.
