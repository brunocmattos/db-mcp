from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime


def configurar_logging(nivel: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, nivel.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


class Auditoria:
    """Trilha de auditoria: uma linha JSON por consulta."""

    def __init__(self, caminho: str) -> None:
        self.caminho = caminho
        # Serializa as escritas: várias requisições concorrentes não podem intercalar
        # linhas no mesmo arquivo.
        self._lock = threading.Lock()

    def registrar(self, *, cliente: str, sql: str, linhas: int, ms: float, veredito: str) -> None:
        registro = {
            "ts": datetime.now(UTC).isoformat(),
            "cliente": cliente,
            "sql": " ".join(sql.split()),  # normaliza espaços
            "linhas": linhas,
            "ms": round(ms, 1),
            "veredito": veredito,
        }
        linha = json.dumps(registro, ensure_ascii=False) + "\n"
        with self._lock, open(self.caminho, "a", encoding="utf-8") as f:
            f.write(linha)
