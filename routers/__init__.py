"""
Routers package
Solo importa routers que realmente existen para evitar fallos al cargar submódulos.
"""

# Importar únicamente módulos presentes en este paquete
from . import (
    # Autenticación
    auth_routes,
    
    
    # Chat e IA
    unified_chat_router,  # ✅ ACTIVADO v4.0 - 17 capacidades integradas
    
    # Búsqueda
    smart_search_router,

    # Documents
    apa7_pdf_router,

    # Class notes
    class_notes_router,
    
    # Voice
    
)

# Lista explícita de exportaciones válidas
__all__ = [
    # Autenticación
    "auth_routes",
    
    # Chat e IA
    "unified_chat_router",
    
    # Búsqueda
    "smart_search_router",

    # Documents
    "apa7_pdf_router",

    # Class notes
    "class_notes_router",
]

__version__ = "1.0.1"
__author__ = "Backend SaaS Ultra Team"
__description__ = "FastAPI routers del proyecto"

def get_all_routers():
    """Retorna una lista de todos los objetos router disponibles sin fallar si alguno no tiene router."""
    routers = []
    for name in __all__:
        module = globals().get(name)
        router = getattr(module, "router", None)
        if router is not None:
            routers.append(router)
    return routers

def get_routes_info():
    """Retorna información resumida de las rutas disponibles."""
    info = {}
    for name in __all__:
        module = globals().get(name)
        router = getattr(module, "router", None)
        if router is None:
            continue
        routes = []
        for route in getattr(router, "routes", []):
            path = getattr(route, "path", None)
            methods = list(getattr(route, "methods", []) or [])
            if path:
                routes.append({"path": path, "methods": methods})
        info[name] = {
            "prefix": getattr(router, "prefix", ""),
            "tags": getattr(router, "tags", []),
            "routes_count": len(routes),
            "routes": routes,
        }
    return info