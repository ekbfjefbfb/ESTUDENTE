"""
Utils Package - Funciones de utilidad
"""

# Importar solo funciones que EXISTEN
from .metrics import (
    setup_metrics, 
    increment_counter, 
    set_gauge,
    observe_histogram,
    http_requests_total,
    db_connections_active
)

# Auth functions - import directo cuando se necesite para evitar circular dependency
# from .auth import (...)

from .rate_limit import rate_limit

__all__ = [
    # Metrics
    "setup_metrics",
    "increment_counter", 
    "set_gauge",
    "observe_histogram",
    "http_requests_total",
    "db_connections_active",
    
    # Rate Limiting
    "rate_limit"
]