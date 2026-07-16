# deployments/ (privado)

Registro de cada ambiente onde o `db-mcp` foi instalado: host, porta, banco,
como o usuário read-only foi criado, faixas de rede liberadas, allowlist escolhida e onde
a senha está guardada.

## Regras

1. Nada aqui (exceto este `README.md` e o `_template.md`) vai pro GitHub. O `.gitignore`
   bloqueia `deployments/*`, o que mantém IPs, senhas e nomes de tabelas reais fora do
   repositório público.
2. Um arquivo por ambiente. Ex.: `homologacao.md`, `producao.md`, `cliente-x.md`.
3. Senha de verdade fica no `.env`/cofre; aqui você só aponta onde ela está.

## Como usar

```bash
cp deployments/_template.md deployments/meu-ambiente.md
# edite meu-ambiente.md com os valores do SEU banco
```

Esse arquivo é o diário de bordo daquele ambiente. Serve pra você, ou pra quem for manter,
reproduzir e entender a instalação depois sem depender da memória de ninguém.
