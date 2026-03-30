"""
Logging Setup Centralizado — Un solo lugar para configurar loggers JSON.

Uso en cualquier módulo:
    from utils.logging_setup import get_logger
    logger = get_logger("mi_modulo")

Elimina el boilerplate repetido de json_log_formatter en 10+ archivos.
"""

import logging
import os
from typing import Optional

# Intentar usar json_log_formatter si está disponible, sino fallback
try:
    import json_log_formatter
    _json_formatter = json_log_formatter.JSONFormatter()
except ImportError:
    _json_formatter = logging.Formatter(
        '{"time": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}'
    )

_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
_configured_loggers: set = set()


def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """
    Retorna un logger JSON estandarizado.
    
    Args:
        name: Nombre del módulo (ej: "auth_service", "rate_limit")
        level: Override de nivel (default: env LOG_LEVEL o INFO)
    
    Returns:
        Logger configurado con formato JSON
    """
    logger = logging.getLogger(name)
    
    # Evitar doble configuración
    if name in _configured_loggers:
        return logger
    
    logger.setLevel(level or _LOG_LEVEL)
    
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_json_formatter)
        logger.addHandler(handler)
    
    # No propagar al root logger para evitar duplicados
    logger.propagate = False
    _configured_loggers.add(name)
    
    return logger
