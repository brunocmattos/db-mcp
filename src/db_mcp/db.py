from __future__ import annotations

from typing import Any

from .config import Settings
from .dialetos import Dialeto, obter_dialeto
from .errors import ConsultaTimeout, ErroBanco


class Database:
    """Fachada fina sobre o pool. Não sabe qual banco está do outro lado — quem sabe
    é o dialeto (pool, cursor-dict, e quais exceções do driver significam o quê)."""

    def __init__(self, s: Settings, dialeto: Dialeto | None = None) -> None:
        self.dialeto = dialeto if dialeto is not None else obter_dialeto(s.dialeto)
        self.pool = self.dialeto.criar_pool(s)

    def executar(
        self, sql: str, max_rows: int, params: Any = None
    ) -> tuple[list[dict[str, Any]], bool]:
        """Roda o SQL (já validado) e devolve (linhas, truncado).

        `params` vai como query parameter do driver — os três drivers do projeto usam
        paramstyle pyformat (%s). É o que mantém a introspecção livre de injeção sem
        depender de regex no nome.
        """
        try:
            with self.pool.connection() as conn, self.dialeto.linhas_como_dict(conn) as cur:
                cur.execute(sql, params)
                linhas = cur.fetchmany(max_rows)
                truncado = cur.fetchone() is not None
            return linhas, truncado
        except Exception as e:
            if self.dialeto.erro_de_timeout(e):
                raise ConsultaTimeout("consulta excedeu o tempo limite") from e
            if self.dialeto.erro_do_banco(e):
                # tabela/coluna inexistente, permissão negada, etc. — vira erro tratado
                # (auditável e com código estável) em vez de escapar cru.
                raise ErroBanco(f"erro do banco: {e}") from e
            raise

    def close(self) -> None:
        self.pool.close()
