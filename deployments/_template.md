# Deployment: <NOME-DO-AMBIENTE>

> Modelo. Copie para `deployments/<ambiente>.md` e preencha. Não coloque a senha aqui;
> aponte onde ela está guardada.

## 1. Identificação
- **Ambiente:** <ex.: homologação / produção>
- **Responsável:** <nome>
- **Data da instalação:** <AAAA-MM-DD>

## 2. Conexão
| Item | Valor |
|---|---|
| Host | `<SEU_HOST>` |
| Porta | `<SUA_PORTA>` |
| Banco(s) | `<SEU_BANCO>` |
| Usuário read-only | `<mcp_ro>` |
| Onde está a senha | `<ex.: cofre X / arquivo /root/….cred>` |
| SSL | `<prefer/require>` |

## 3. Como o usuário read-only foi criado
<Cole aqui os comandos exatos que você rodou (ver docs/02-preparar-o-banco.md), já com os
valores deste ambiente. Serve de histórico e de "desfazer" se precisar.>

## 4. Rede liberada (pg_hba)
<Quais faixas/IPs foram liberadas para o usuário read-only, e por quê.>

## 5. Allowlist escolhida
<Quais schemas/tabelas/views foram liberados para este ambiente e o motivo.>

## 6. Parâmetros (config.yaml)
<Limites diferentes do default? MAX_ROWS, RATE_LIMIT_PER_MIN, transporte, etc.>

## 7. Verificação (doctor)
<Resultado do `pg-readonly-mcp doctor` na última execução: passou/falhou em cada checagem.>

## 8. Notas de segurança
<Qualquer coisa relevante: banco exposto? VPN obrigatória? rotação de senha?>
