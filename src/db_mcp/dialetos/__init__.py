from __future__ import annotations

from collections.abc import Callable

from .base import Dialeto, Perfil, PoolLike

__all__ = ["DIALETOS_IMPLEMENTADOS", "Dialeto", "Perfil", "PoolLike", "obter_dialeto"]


def _postgres() -> Dialeto:
    from .postgres import DialetoPostgres

    return DialetoPostgres()


# Registro dos dialetos com implementação — a FONTE ÚNICA da verdade. `obter_dialeto` e o
# teste de invariante (tests/test_dialetos.py) bebem daqui, então quem acrescentar um
# dialeto não pode escapar do gate. Cada valor é uma fábrica que importa o módulo do driver
# lazy: quem usa só um banco não paga os outros. Fases 1 e 2 entram com uma linha cada.
_REGISTRO: dict[str, Callable[[], Dialeto]] = {
    "postgres": _postgres,
}

# Nomes com implementação de fato. NÃO é o mesmo conjunto do Literal do config (que ACEITA
# "mysql"/"sqlserver" por antecipação): aqui só entra o que `obter_dialeto` resolve hoje.
DIALETOS_IMPLEMENTADOS: tuple[str, ...] = tuple(_REGISTRO)


def obter_dialeto(nome: str) -> Dialeto:
    """Instancia o dialeto pelo nome.

    Importa o módulo lazy (via a fábrica no _REGISTRO): o driver de cada banco é um extra
    opcional, e quem usa só um banco não deve precisar dos outros instalados.

    A config aceita "mysql" e "sqlserver" (valores válidos do Literal), mas eles só ganham
    fábrica aqui nas Fases 1 e 2 — até lá, caem no erro legível abaixo.
    """
    fabrica = _REGISTRO.get(nome)
    if fabrica is None:
        raise ValueError(f"dialeto desconhecido: {nome!r}")
    return fabrica()
