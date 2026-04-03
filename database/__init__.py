"""
Compatibilidad del paquete `database`.

Muchos módulos importan `SessionLocal` y `get_db` desde `database`.
Re-exportamos explícitamente la API pública usada por routers y servicios.
"""

from database.database import (
    Base,
    SessionLocal,
    close_db,
    get_async_db,
    get_db,
    get_db_sync,
    init_db,
)

__all__ = [
    "Base",
    "SessionLocal",
    "get_db",
    "get_db_sync",
    "get_async_db",
    "init_db",
    "close_db",
]
