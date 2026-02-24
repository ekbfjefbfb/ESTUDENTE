"""
Services Package - Mi Backend Super IA

IMPORTANTE: No importar servicios automáticamente para evitar circular imports.
Los routers deben importar directamente:
    from services.auth_service import AuthService
    from services.gpt_service import chat_with_ai
    etc.
"""

# Slim build: do not import submodules here.
__all__ = []