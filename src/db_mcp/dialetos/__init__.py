from __future__ import annotations

from .base import Dialeto, Perfil, PoolLike

__all__ = ["Dialeto", "Perfil", "PoolLike", "obter_dialeto"]


def obter_dialeto(nome: str) -> Dialeto:
    """Instancia o dialeto pelo nome.

    Importa o módulo lazy: o driver de cada banco é um extra opcional, e quem usa só
    um banco não deve precisar dos outros instalados.

    A config aceita "mysql" e "sqlserver" (são valores válidos do Literal), mas eles só
    ganham ramo aqui nas Fases 1 e 2 — até lá, caem no erro legível abaixo.
    """
    if nome == "postgres":
        from .postgres import DialetoPostgres

        return DialetoPostgres()
    raise ValueError(f"dialeto desconhecido: {nome!r}")
