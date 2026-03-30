"""
BoundedDict — Dict con tamaño máximo y TTL automático.

Previene memory leaks en caches in-memory como:
- user_contexts en groq_ai_service.py
- user_request_counts en utils/auth.py  
- query_cache en db_enterprise.py

Uso:
    cache = BoundedDict(max_size=1000, ttl_seconds=3600)
    cache["key"] = "value"
    val = cache.get("key")  # None si expiró
"""

import time
from collections import OrderedDict
from typing import Any, Optional


class BoundedDict:
    """Dict thread-safe con tamaño máximo (LRU) y TTL por entrada."""

    __slots__ = ("_max_size", "_ttl", "_data", "_timestamps")

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._data: OrderedDict = OrderedDict()
        self._timestamps: dict = {}

    # ---- Interfaz dict-like ----

    def __setitem__(self, key: str, value: Any) -> None:
        now = time.monotonic()
        
        # Si la key ya existe, moverla al final (LRU)
        if key in self._data:
            self._data.move_to_end(key)
        
        self._data[key] = value
        self._timestamps[key] = now
        
        # Evict si excede max_size
        while len(self._data) > self._max_size:
            oldest_key, _ = self._data.popitem(last=False)
            self._timestamps.pop(oldest_key, None)

    def __getitem__(self, key: str) -> Any:
        val = self.get(key)
        if val is None:
            raise KeyError(key)
        return val

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

    def __len__(self) -> int:
        return len(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        """Retorna valor si existe y no expiró, sino default."""
        if key not in self._data:
            return default
        
        # Verificar TTL
        created = self._timestamps.get(key, 0)
        if time.monotonic() - created > self._ttl:
            # Expirado — limpiar
            self._data.pop(key, None)
            self._timestamps.pop(key, None)
            return default
        
        # Mover al final (LRU)
        self._data.move_to_end(key)
        return self._data[key]

    def pop(self, key: str, default: Any = None) -> Any:
        """Elimina y retorna valor."""
        self._timestamps.pop(key, None)
        return self._data.pop(key, default)

    def clear(self) -> None:
        """Vacía todo."""
        self._data.clear()
        self._timestamps.clear()

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()
