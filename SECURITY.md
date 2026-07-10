# Política de segurança

## Versões suportadas

O projeto está em `0.x`. Correções de segurança vão para a `main` e para a
próxima release; não há suporte retroativo a versões antigas.

| Versão | Suportada |
|--------|-----------|
| 0.1.x  | ✅        |

## Como reportar

Não abra uma issue pública. Use o **Report a vulnerability** na aba *Security*
do repositório no GitHub (GitHub Private Security Advisories) — o relato fica
privado até a correção sair.

Inclua o que conseguir: versão, como reproduzir, e o impacto que você enxerga.
Respondo no melhor esforço; este é um projeto mantido nas horas vagas, então não
prometo SLA, mas falhas que furem os cadeados de read-only têm prioridade.

## Escopo

O que mais interessa: qualquer caminho que faça o servidor **escrever**, alterar
schema, escapar da allowlist de tabelas, burlar os tetos de linhas/bytes ou o
rate limit, ou vazar dados que a config não deveria expor. As três camadas de
defesa (usuário read-only no banco, `pg_hba` por IP, validador SQL na aplicação)
existem justamente pra isso — relatos que contornem qualquer uma delas são bem-vindos.
