---
name: setup-db-mcp
description: Use quando o usuário quiser INSTALAR/CONFIGURAR o db-mcp apontando pro banco PostgreSQL dele — pergunta os parâmetros de conexão, ajuda a criar o usuário read-only, escreve .env/config.yaml, roda o doctor e registra o MCP no cliente. Dispare com pedidos como "instala o db-mcp", "configura o MCP read-only no meu banco", "conecta isso no meu Postgres".
---

# Instalar o db-mcp

Você vai guiar o usuário a instalar este projeto apontando pro Postgres dele. Trabalhe na
raiz do projeto (onde estão `pyproject.toml` e `.env.example`). Não comite segredos: `.env`
e `config.yaml` são git-ignored.

## Passo 1: coletar os parâmetros do banco

Pergunte (um bloco só): host, porta (default 5432), nome do banco, usuário read-only (default
`mcp_ro`), senha, sslmode (default `prefer`). Pergunte também se ele já tem o usuário
read-only criado.

## Passo 2: usuário read-only (se ainda não existe)

Se não existe, mostre o SQL de `docs/02-preparar-o-banco.md` com os valores dele preenchidos,
e peça pra ele rodar no banco como admin. Deixe claro: só `GRANT SELECT` +
`default_transaction_read_only = on`. Peça também a linha do `pg_hba.conf` liberando o IP da
máquina. Espere ele confirmar que rodou.

## Passo 3: escrever a config

Escreva `.env` a partir de `.env.example` com os valores coletados. Se ele quiser restringir
tabelas ou ajustar limites, copie `config.example.yaml` para `config.yaml` e ajuste
`allowlist`/`max_rows`/etc. Confirme que os dois estão git-ignored (`git check-ignore .env`).

## Passo 4: instalar e verificar

Rode `uv sync`, depois `uv run db-mcp doctor`. Leia a saída e, para cada `[X]`,
explique a causa e a correção (use `docs/04-troubleshooting.md`). Não prossiga enquanto o
doctor não sair com código 0. A checagem "Somente-leitura confirmado" é a crítica: se ela
falha, o usuário do banco consegue escrever, o que é um problema de segurança real a corrigir
nos GRANTs.

## Passo 5: registrar no cliente MCP

Pergunte qual cliente ele usa.

- Claude Code: rode
  `claude mcp add --scope user db-mcp -- uv run --directory <CAMINHO_ABSOLUTO> db-mcp`
  (substitua `<CAMINHO_ABSOLUTO>` pela raiz do projeto). Confirme com `claude mcp list`.
- Claude Desktop: entregue o JSON pra ele colar em
  `%APPDATA%\Claude\claude_desktop_config.json` (Windows) ou
  `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS), com `command: "uv"`
  e `args: ["run", "--directory", "<CAMINHO_ABSOLUTO>", "db-mcp"]`. Lembre de escapar
  `\\` no Windows e reiniciar o app.

Como o servidor lê o `.env` da pasta do projeto, não coloque segredos na config do cliente.

O transporte padrão é stdio, que não usa autenticação. Se ele for expor por HTTP
(`TRANSPORT=http`), o servidor exige `AUTH_TOKEN` e recusa subir sem ele.

## Passo 6: confirmar

Resuma o que foi feito (banco apontado, doctor verde, cliente registrado) e sugira testar
pedindo ao agente para `listar_schemas` ou `descrever_tabela`.
