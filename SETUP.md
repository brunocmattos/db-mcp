# SETUP — instalação assistida pelo Claude

O Claude Code pode fazer a instalação por você.

## Como usar

1. Instale o [Claude Code](https://code.claude.com) e o [`uv`](https://docs.astral.sh/uv/).
2. Abra esta pasta (`pg-readonly-mcp`) no Claude Code.
3. Peça:

   > "Instala o pg-readonly-mcp apontando pro meu banco."

O Claude executa a skill `setup-pg-readonly-mcp`, que pergunta os parâmetros do seu
Postgres (host, porta, banco, usuário, senha, sslmode), te dá o SQL pronto pra criar o
usuário read-only pra você rodar no seu banco (ver
[`docs/02-preparar-o-banco.md`](docs/02-preparar-o-banco.md)), escreve o `.env` (e um
`config.yaml` se você quiser ajustar allowlist/limites), roda `uv sync` e
`uv run pg-readonly-mcp doctor` interpretando cada checagem, e registra o MCP no seu
cliente (Claude Code via `claude mcp add`, ou o JSON do Claude Desktop pra você colar).

Nenhum segredo entra no repositório: o `.env` é git-ignored e a config do cliente só
aponta pro comando.

Instalado, peça algo como "lista os schemas" ou "descreve a tabela X" pra ver o
`listar_schemas` e o `descrever_tabela` respondendo.

## Instalação manual

Siga [`docs/01-instalacao.md`](docs/01-instalacao.md).
