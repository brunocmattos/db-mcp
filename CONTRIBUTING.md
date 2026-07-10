# Contribuindo

Projeto pequeno, processo curto.

## Ambiente

Requer Python 3.11+ e o [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync                 # instala tudo, incluindo as dependências de dev
uv run pytest -q        # roda a suíte
```

Os testes de integração, E2E e o `doctor` contra um banco real só rodam se você
tiver um PostgreSQL alcançável e um `.env` apontando pra ele. Sem isso, eles se
pulam sozinhos — os testes unitários passam offline.

## Antes de abrir um PR

Rode as três verificações que o CI também roda:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
```

`ruff format .` arruma a formatação; `ruff check --fix .` resolve boa parte dos
apontamentos de lint automaticamente.

## Fluxo

- Trabalhe numa branch a partir da `main` (`git checkout -b feat/algo`).
- Um assunto por PR. Mensagens de commit no imperativo, explicando o *porquê*
  quando não for óbvio.
- Toque de código pede teste. Se mudar comportamento de segurança (o validador
  SQL, a allowlist, os tetos), o teste é obrigatório.
- CI verde antes do merge.

## Segurança

Não abra issue pública para falhas de segurança. Veja [`SECURITY.md`](SECURITY.md).
