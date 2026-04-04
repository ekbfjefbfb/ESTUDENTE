"""
CSRF Protection Middleware - Enterprise Security
Protección contra Cross-Site Request Forgery en endpoints críticos
Versión: 1.0 - Noviembre 2025
"""

import hashlib
import hmac
import secrets
import time
from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger("csrf_middleware")

# Endpoints que requieren CSRF protection
CSRF_PROTECTED_PATHS = [
    "/api/payments/",
    "/api/subscriptions/subscribe",
    "/api/permissions/grant",
    "/api/permissions/revoke",
    "/api/invitations/",
]

# Métodos HTTP que requieren CSRF
CSRF_PROTECTED_METHODS = ["POST", "PUT", "DELETE", "PATCH"]

# Secret key para CSRF tokens (debe ser la misma que JWT)
CSRF_SECRET_KEY = None

class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Middleware de protección CSRF
    
    Genera y valida tokens CSRF para endpoints críticos
    """
    
    def __init__(self, app, secret_key: str):
        super().__init__(app)
        global CSRF_SECRET_KEY
        CSRF_SECRET_KEY = secret_key
        logger.info("✅ CSRF Protection Middleware initialized")
    
    async def dispatch(self, request: Request, call_next):
        """
        Procesa cada request verificando CSRF en endpoints críticos
        """
        
        # Solo validar en métodos que modifican datos
        if request.method not in CSRF_PROTECTED_METHODS:
            return await call_next(request)
        
        # Verificar si el path requiere CSRF
        path = request.url.path
        requires_csrf = any(path.startswith(protected) for protected in CSRF_PROTECTED_PATHS)
        
        if not requires_csrf:
            return await call_next(request)
        
        # Excepciones: webhooks de pagos (tienen su propia validación)
        if "/webhook/" in path:
            return await call_next(request)
        
        # Obtener token CSRF del header
        csrf_token = request.headers.get("X-CSRF-Token")
        
        if not csrf_token:
            logger.warning(f"CSRF token missing for {path}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "success": False,
                    "error": "csrf_token_missing",
                    "message": "CSRF token missing. Include X-CSRF-Token header."
                }
            )
        
        # Validar token CSRF
        if not self._validate_csrf_token(csrf_token):
            logger.warning(f"Invalid CSRF token for {path}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "success": False,
                    "error": "csrf_token_invalid",
                    "message": "Invalid CSRF token"
                }
            )
        
        # Token válido, continuar
        response = await call_next(request)
        return response
    
    def _validate_csrf_token(self, token: str) -> bool:
        """
        Valida un token CSRF
        
        Formato del token: timestamp:random:signature
        """
        try:
            parts = token.split(":")
            if len(parts) != 3:
                return False
            
            timestamp_str, random_part, signature = parts
            timestamp = int(timestamp_str)
            
            # Verificar que el token no haya expirado (15 minutos)
            current_time = int(time.time())
            if current_time - timestamp > 900:  # 15 minutos
                logger.warning("CSRF token expired")
                return False
            
            # Verificar firma
            expected_signature = self._generate_signature(timestamp_str, random_part)
            
            # Comparación segura contra timing attacks
            return hmac.compare_digest(signature, expected_signature)
            
        except Exception as e:
            logger.error(f"CSRF validation error: {e}")
            return False
    
    def _generate_signature(self, timestamp: str, random_part: str) -> str:
        """
        Genera la firma HMAC del token CSRF
        """
        key = CSRF_SECRET_KEY
        if not key:
            raise RuntimeError("CSRF secret key not configured")
        message = f"{timestamp}:{random_part}"
        signature = hmac.new(
            key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature


def generate_csrf_token() -> str:
    """
    Genera un nuevo token CSRF
    
    Returns:
        Token CSRF en formato: timestamp:random:signature
    """
    key = CSRF_SECRET_KEY
    if not key:
        raise RuntimeError("CSRF secret key not configured")
    timestamp = str(int(time.time()))
    random_part = secrets.token_urlsafe(32)
    
    message = f"{timestamp}:{random_part}"
    signature = hmac.new(
        key.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    
    token = f"{timestamp}:{random_part}:{signature}"
    return token


# Endpoint helper para obtener token CSRF
async def get_csrf_token() -> dict:
    """
    Genera y retorna un nuevo token CSRF
    
    Usage en router:
        from middlewares.csrf_middleware import get_csrf_token
        
        @router.get("/csrf-token")
        async def csrf_token():
            return await get_csrf_token()
    """
    global CSRF_SECRET_KEY
    if not CSRF_SECRET_KEY:
        from config import SECRET_KEY
        CSRF_SECRET_KEY = SECRET_KEY
    
    token = generate_csrf_token()
    return {
        "csrf_token": token,
        "expires_in": 900,  # 15 minutos
        "usage": "Include in X-CSRF-Token header for protected requests"
    }
