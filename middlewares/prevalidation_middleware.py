"""
Middleware de Pre-validación Automática
Optimiza el flujo de requests con validaciones rápidas y caché
"""

import logging
import time
from typing import Callable, Dict, Any, Optional
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# from services.smart_cache_service import smart_cache  # TODO: Implementar smart_cache_service
from services.anti_abuse_service import anti_abuse_service
from utils.auth import decode_access_token
import json_log_formatter

# Stub temporal para smart_cache
class SmartCacheStub:
    async def get(self, key: str):
        return None
    async def set(self, key: str, value: Any, ttl: int = 60):
        pass

smart_cache = SmartCacheStub()

# =============================================
# CONFIGURACIÓN DE LOGGING
# =============================================
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("prevalidation_middleware")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

class PreValidationMiddleware(BaseHTTPMiddleware):
    """
    Middleware de pre-validación que optimiza el flujo de requests
    - Validaciones rápidas desde caché
    - Pre-autenticación
    - Rate limiting inteligente
    """
    
    def __init__(self, app):
        super().__init__(app)
        # Rutas que requieren validación completa
        self.protected_routes = {
            "/api/chat/",
            "/api/documents/",
            "/api/smart-search/",
            "/api/smart-voice/",
            "/api/personal-agents/",
            "/api/livesearch/"
        }
        
        # Rutas que no requieren validación (públicas)
        self.public_routes = {
            "/health",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/api/auth/login",
            "/api/auth/register",
            "/api/auth/refresh"
        }
        
        # Cache para validaciones rápidas
        self.validation_cache_ttl = 30  # 30 segundos
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Procesa el request con pre-validaciones optimizadas."""
        start_time = time.time()
        
        try:
            # Saltar validación para rutas públicas
            if self._is_public_route(request.url.path):
                response = await call_next(request)
                self._log_request(request, response, time.time() - start_time, "public")
                return response
            
            # Pre-validación rápida para rutas protegidas
            if self._requires_validation(request.url.path):
                validation_result = await self._fast_prevalidation(request)
                
                if not validation_result["valid"]:
                    # Retornar error inmediatamente sin procesar el request
                    self._log_request(request, None, time.time() - start_time, "blocked", validation_result["reason"])
                    return JSONResponse(
                        status_code=validation_result["status_code"],
                        content={
                            "error": validation_result["reason"],
                            "details": validation_result.get("details", {}),
                            "timestamp": time.time()
                        }
                    )
                
                # Agregar datos de validación al request para uso posterior
                request.state.validation_data = validation_result["data"]
                request.state.user_id = validation_result["user_id"]
                request.state.user_plan = validation_result["user_plan"]
            
            # Procesar request normalmente
            response = await call_next(request)
            
            # Post-procesamiento asíncrono (no bloquea respuesta)
            self._schedule_background_tasks(request, response)
            
            self._log_request(request, response, time.time() - start_time, "success")
            return response
            
        except Exception as e:
            logger.error({
                "event": "prevalidation_middleware_error",
                "path": request.url.path,
                "method": request.method,
                "error": str(e),
                "duration": time.time() - start_time
            })
            
            # Continuar con el flujo normal si hay error en middleware
            response = await call_next(request)
            return response
    
    def _is_public_route(self, path: str) -> bool:
        """Verifica si la ruta es pública."""
        return any(public_path in path for public_path in self.public_routes)
    
    def _requires_validation(self, path: str) -> bool:
        """Verifica si la ruta requiere validación."""
        return any(protected_path in path for protected_path in self.protected_routes)
    
    async def _fast_prevalidation(self, request: Request) -> Dict[str, Any]:
        """
        Realiza pre-validación rápida usando caché
        
        Returns:
            Dict con resultado de validación
        """
        try:
            # 1. Extraer token de autorización
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return {
                    "valid": False,
                    "reason": "missing_or_invalid_authorization_header",
                    "status_code": status.HTTP_401_UNAUTHORIZED
                }
            
            token = auth_header.split(" ")[1]
            
            # 2. Validar token desde caché
            token_data = await self._validate_token_cached(token)
            if not token_data["valid"]:
                return {
                    "valid": False,
                    "reason": "invalid_or_expired_token",
                    "status_code": status.HTTP_401_UNAUTHORIZED
                }
            
            user_id = token_data["user_id"]
            
            # 3. Verificar rate limiting desde caché
            rate_limit_result = await self._check_rate_limit_cached(user_id)
            if not rate_limit_result["allowed"]:
                return {
                    "valid": False,
                    "reason": "rate_limit_exceeded",
                    "status_code": status.HTTP_429_TOO_MANY_REQUESTS,
                    "details": rate_limit_result
                }
            
            # 4. Obtener plan del usuario desde caché
            user_plan = await smart_cache.get_or_set(
                "user_plan",
                user_id,
                lambda: anti_abuse_service.get_user_plan(user_id),
                ttl=600
            )
            
            return {
                "valid": True,
                "user_id": user_id,
                "user_plan": user_plan,
                "data": {
                    "token_data": token_data,
                    "rate_limit": rate_limit_result,
                    "plan": user_plan
                }
            }
            
        except Exception as e:
            logger.error({
                "event": "fast_prevalidation_error",
                "error": str(e)
            })
            return {
                "valid": False,
                "reason": "validation_error",
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR
            }
    
    async def _validate_token_cached(self, token: str) -> Dict[str, Any]:
        """Valida token JWT usando caché."""
        try:
            # Intentar obtener del caché primero
            cache_key = f"token_validation:{token[-10:]}"  # Últimos 10 chars como key
            
            async def validate_token():
                try:
                    payload = decode_access_token(token)
                    if payload and "sub" in payload:
                        return {
                            "valid": True,
                            "user_id": payload["sub"],
                            "payload": payload
                        }
                    return {"valid": False}
                except Exception:
                    return {"valid": False}
            
            result = await smart_cache.get_or_set(
                "auth_token",
                cache_key,
                validate_token,
                ttl=300  # 5 minutos
            )
            
            return result
            
        except Exception as e:
            logger.error({
                "event": "token_validation_error",
                "error": str(e)
            })
            return {"valid": False}
    
    async def _check_rate_limit_cached(self, user_id: str) -> Dict[str, Any]:
        """Verifica rate limiting usando caché."""
        try:
            # Verificar estado reciente del rate limit
            cached_status = await smart_cache.get("rate_limit_status", f"{user_id}:minute")
            
            if cached_status:
                # Si está en caché y no está bloqueado, permitir
                if not cached_status.get("blocked", False):
                    return {"allowed": True, "cached": True, "data": cached_status}
                else:
                    return {"allowed": False, "reason": "rate_limit_cached", "data": cached_status}
            
            # No está en caché, hacer verificación completa
            can_proceed, rate_info = await anti_abuse_service.check_rate_limit(user_id)
            
            return {
                "allowed": can_proceed,
                "reason": "fresh_check" if can_proceed else rate_info.get("reason", "rate_limited"),
                "data": rate_info
            }
            
        except Exception as e:
            logger.error({
                "event": "rate_limit_check_error",
                "user_id": user_id,
                "error": str(e)
            })
            # En caso de error, permitir (fail-open)
            return {"allowed": True, "reason": "error_fallback"}
    
    def _schedule_background_tasks(self, request: Request, response: Response):
        """Programa tareas en background (no bloquea respuesta)."""
        try:
            # Aquí se pueden agregar tareas asíncronas como:
            # - Logging detallado
            # - Actualización de métricas
            # - Análisis de uso
            # - Limpieza de caché
            pass
        except Exception as e:
            logger.error({
                "event": "background_task_error",
                "error": str(e)
            })
    
    def _log_request(self, request: Request, response: Optional[Response], duration: float, status: str, reason: str = None):
        """Log optimizado de requests."""
        log_data = {
            "event": "request_processed",
            "method": request.method,
            "path": request.url.path,
            "status": status,
            "duration_ms": round(duration * 1000, 2),
            "timestamp": time.time()
        }
        
        if response:
            log_data["status_code"] = response.status_code
        
        if reason:
            log_data["reason"] = reason
        
        if hasattr(request.state, "user_id"):
            log_data["user_id"] = request.state.user_id
            log_data["user_plan"] = getattr(request.state, "user_plan", None)
        
        if status == "blocked":
            logger.warning(log_data)
        else:
            logger.info(log_data)