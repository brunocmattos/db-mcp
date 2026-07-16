from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class _Bucket:
    tokens: float
    atualizado: float


@dataclass
class RateLimiter:
    """Token-bucket por cliente: `por_minuto` fichas, repostas ao longo do tempo."""

    por_minuto: int
    _buckets: dict[str, _Bucket] = field(default_factory=dict)
    # Sob HTTP o servidor atende requisições em paralelo; o lock evita que duas
    # concedam a mesma ficha ao mesmo tempo (e estourem o limite).
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def permitir(self, cliente: str, agora: float | None = None) -> bool:
        agora = time.monotonic() if agora is None else agora
        taxa = self.por_minuto / 60.0
        with self._lock:
            b = self._buckets.get(cliente)
            if b is None:
                b = _Bucket(tokens=float(self.por_minuto), atualizado=agora)
                self._buckets[cliente] = b
            # reabastece proporcional ao tempo passado
            b.tokens = min(self.por_minuto, b.tokens + (agora - b.atualizado) * taxa)
            b.atualizado = agora
            if b.tokens >= 1.0:
                b.tokens -= 1.0
                return True
            return False
