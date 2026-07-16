# 01 — Instalação

Guia genérico. Os valores concretos aqui são placeholders; troque pelos seus.

> Só quer ver funcionando sem preparar um banco? A seção **"Experimente em 30 segundos"**
> do [README](../README.md) sobe um Postgres de demonstração em Docker, já pronto.

## Passo 0: prepare o banco antes do doctor

O `doctor` só fica verde com o banco já preparado: usuário read-only `mcp_ro`
criado e o `pg_hba.conf` liberando o acesso dele. Isso está em
[`02-preparar-o-banco.md`](02-preparar-o-banco.md) e é pré-requisito das checagens
de auth e de read-only. Faça esse passo antes de seguir.

## Pré-requisitos

- Python 3.11+ (o projeto fixa a 3.12 via `.python-version`; o CI testa 3.12 e 3.13).
- [`uv`](https://docs.astral.sh/uv/) instalado.
- Rede até o banco: a máquina que roda o MCP precisa alcançar `PG_HOST:PG_PORT`,
  muitas vezes por VPN. Sem isso, o `doctor` falha em "TCP inacessível".
- O usuário read-only do Passo 0.

## 1. Instalar as dependências

```bash
uv sync
```

> Windows: se o `uv` reclamar da versão do Python, aponte o interpretador:
> `uv sync --python 3.12`.

## 2. Preencher a config

Segredos em `.env`, ajustes em `config.yaml`:

```bash
cp .env.example .env
cp config.example.yaml config.yaml   # opcional; sem ele, valem os defaults
```

Edite `.env` (exemplo com placeholders):

```dotenv
PG_HOST=SEU_HOST
PG_PORT=5432
PG_DBNAME=SEU_BANCO
PG_USER=mcp_ro
PG_PASSWORD=SUA_SENHA
PG_SSLMODE=prefer
```

`.env` e `config.yaml` são git-ignored e nunca sobem pro repositório.

## 3. Verificar

```bash
uv run db-mcp doctor
```

Deve mostrar 6 checagens e sair com código `0`. Cada `[X]` vem com a remediação;
detalhes em [`04-troubleshooting.md`](04-troubleshooting.md). Se as checagens de auth
ou de read-only falharem, é sinal de que o Passo 0 ainda não foi feito.

## 4. Subir o servidor (dev, stdio)

```bash
uv run db-mcp
```

## 5. Registrar no cliente MCP

O servidor lê o `.env` da própria pasta do projeto, então não é preciso colocar
segredo na config do cliente; basta apontar pro comando.

### Claude Code (CLI)

```bash
# escopo "user" = disponível em todos os seus projetos
claude mcp add --scope user db-mcp \
  -- uv run --directory /CAMINHO/ABSOLUTO/db-mcp db-mcp
```

Confira com `claude mcp list` e `claude mcp get db-mcp`. O `--directory` é
obrigatório: o cliente sobe o processo de um diretório qualquer, e é ele que faz o
`uv` achar o projeto (e o `.env`).

### Claude Code (arquivo de projeto `.mcp.json`)

Para compartilhar com o time via git, sem segredos (cada um define suas vars de ambiente):

```json
{
  "mcpServers": {
    "db-mcp": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--directory", "${CLAUDE_PROJECT_DIR:-.}", "db-mcp"]
    }
  }
}
```

### Claude Desktop

Edite o arquivo de config (Settings → Developer → Edit Config, ou direto):

- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "db-mcp": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\CAMINHO\\ABSOLUTO\\db-mcp", "db-mcp"]
    }
  }
}
```

No Windows, escape as barras (`\\`). Se `uv` não estiver no PATH que o app herda, use o
caminho absoluto do `uv` (descubra com `where uv` / `which uv`). Feche e reabra o Claude
Desktop após editar.

## 6. Produção (servidor HTTP com token)

Para rodar como serviço acessível pela rede, use `TRANSPORT=http` com um serviço
`systemd`. Nesse modo o `AUTH_TOKEN` é obrigatório: o servidor valida o token como
Bearer em toda requisição e recusa subir sem ele. Em `config.yaml`:

```yaml
transport: http
http_host: 0.0.0.0
http_port: 8080
```

Defina `AUTH_TOKEN` no `.env`. Exemplo de unit (`/etc/systemd/system/db-mcp.service`):

```ini
[Unit]
Description=db-mcp (MCP somente-leitura para PostgreSQL)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=SEU_USUARIO_DE_SERVICO
WorkingDirectory=/CAMINHO/ABSOLUTO/db-mcp
ExecStart=/CAMINHO/PARA/uv run db-mcp
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now db-mcp
```

Problemas? [`04-troubleshooting.md`](04-troubleshooting.md).
