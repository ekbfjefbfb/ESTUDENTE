"""
Servicio de Pre-autenticación Optimizada
Sistema de tokens de sesión para evitar re-validaciones
"""

import logging
import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List
import uuid

from services.smart_cache_service import smart_cache
from services.redis_service import get_redis_client
from utils.auth import decode_access_token, create_access_token
import json_log_formatter

# =============================================
# CONFIGURACIÓN DE LOGGING
# =============================================
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("preauth_service")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

class PreAuthService:
    """
    Servicio de pre-autenticación con tokens de sesión optimizados
    Reduce validaciones repetitivas y mejora performance
    """
    
    def __init__(self):
        self.session_ttl = 1800  # 30 minutos
        self.quick_check_ttl = 300  # 5 minutos para verificaciones rápidas
        
    async def create_session_token(self, user_id: str, user_data: Dict[str, Any]) -> str:
        """
        Crea un token de sesión optimizado
        
        Args:
            user_id: ID del usuario
            user_data: Datos del usuario (plan, permisos, etc.)
            
        Returns:
            Token de sesión
        """
        try:
            # Generar ID único para la sesión
            session_id = str(uuid.uuid4())
            
            # Datos de la sesión
            session_data = {
                "user_id": user_id,
                "session_id": session_id,
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(seconds=self.session_ttl)).isoformat(),
                "user_data": user_data,
                "permissions": self._extract_permissions(user_data),
                "plan_limits": self._extract_plan_limits(user_data)
            }
            
            # Guardar en caché con TTL
            session_key = f"session:{session_id}"
            await smart_cache.set(
                "auth_token",
                session_key,
                session_data,
                ttl=self.session_ttl
            )
            
            # También mantener mapeo user_id -> session_id
            user_session_key = f"user_session:{user_id}"
            await smart_cache.set(
                "auth_token",
                user_session_key,
                session_id,
                ttl=self.session_ttl
            )
            
            logger.info({
                "event": "session_token_created",
                "user_id": user_id,
                "session_id": session_id,
                "ttl": self.session_ttl
            })
            
            return session_id
            
        except Exception as e:
            logger.error({
                "event": "session_token_creation_error",
                "user_id": user_id,
                "error": str(e)
            })
            return None
    
    async def validate_session_token(self, session_token: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Valida un token de sesión
        
        Args:
            session_token: Token de sesión a validar
            
        Returns:
            Tuple[bool, dict]: (is_valid, session_data)
        """
        try:
            session_key = f"session:{session_token}"
            session_data = await smart_cache.get("auth_token", session_key)
            
            if not session_data:
                return False, None
            
            # Verificar expiración
            expires_at = datetime.fromisoformat(session_data["expires_at"])
            if datetime.utcnow() > expires_at:
                # Limpiar sesión expirada
                await self._cleanup_session(session_token, session_data["user_id"])
                return False, None
            
            # Actualizar última actividad
            session_data["last_activity"] = datetime.utcnow().isoformat()
            await smart_cache.set(
                "auth_token",
                session_key,
                session_data,
                ttl=self.session_ttl
            )
            
            logger.debug({
                "event": "session_validated",
                "session_id": session_token,
                "user_id": session_data["user_id"]
            })
            
            return True, session_data
            
        except Exception as e:
            logger.error({
                "event": "session_validation_error",
                "session_token": session_token,
                "error": str(e)
            })
            return False, None
    
    async def refresh_session(self, session_token: str) -> Optional[str]:
        """
        Renueva una sesión existente
        
        Args:
            session_token: Token de sesión actual
            
        Returns:
            Nuevo token de sesión o None si falla
        """
        try:
            is_valid, session_data = await self.validate_session_token(session_token)
            if not is_valid or not session_data:
                return None
            
            # Crear nueva sesión con datos actualizados
            new_session_token = await self.create_session_token(
                session_data["user_id"],
                session_data["user_data"]
            )
            
            # Limpiar sesión anterior
            await self._cleanup_session(session_token, session_data["user_id"])
            
            logger.info({
                "event": "session_refreshed",
                "old_session": session_token,
                "new_session": new_session_token,
                "user_id": session_data["user_id"]
            })
            
            return new_session_token
            
        except Exception as e:
            logger.error({
                "event": "session_refresh_error",
                "session_token": session_token,
                "error": str(e)
            })
            return None
    
    async def invalidate_session(self, session_token: str) -> bool:
        """
        Invalida una sesión específica
        
        Args:
            session_token: Token de sesión a invalidar
            
        Returns:
            True si se invalidó correctamente
        """
        try:
            session_key = f"session:{session_token}"
            session_data = await smart_cache.get("auth_token", session_key)
            
            if session_data:
                user_id = session_data["user_id"]
                await self._cleanup_session(session_token, user_id)
                
                logger.info({
                    "event": "session_invalidated",
                    "session_id": session_token,
                    "user_id": user_id
                })
                
                return True
            
            return False
            
        except Exception as e:
            logger.error({
                "event": "session_invalidation_error",
                "session_token": session_token,
                "error": str(e)
            })
            return False
    
    async def invalidate_all_user_sessions(self, user_id: str) -> int:
        """
        Invalida todas las sesiones de un usuario
        
        Args:
            user_id: ID del usuario
            
        Returns:
            Número de sesiones invalidadas
        """
        try:
            # Buscar todas las sesiones del usuario
            pattern = f"session:*"
            redis_client = await get_redis_client()
            session_keys = await redis_client.keys(pattern)
            
            invalidated_count = 0
            
            for session_key in session_keys:
                session_data = await smart_cache.get("auth_token", session_key.decode())
                if session_data and session_data.get("user_id") == user_id:
                    session_token = session_key.decode().split(":")[-1]
                    await self._cleanup_session(session_token, user_id)
                    invalidated_count += 1
            
            logger.info({
                "event": "all_user_sessions_invalidated",
                "user_id": user_id,
                "sessions_invalidated": invalidated_count
            })
            
            return invalidated_count
            
        except Exception as e:
            logger.error({
                "event": "user_sessions_invalidation_error",
                "user_id": user_id,
                "error": str(e)
            })
            return 0
    
    async def quick_auth_check(self, session_token: str) -> Dict[str, Any]:
        """
        Verificación rápida de autenticación para requests frecuentes
        
        Args:
            session_token: Token de sesión
            
        Returns:
            Dict con información básica de autenticación
        """
        try:
            # Crear clave de verificación rápida
            quick_key = f"quick_auth:{session_token}"
            
            # Intentar obtener del caché rápido
            quick_data = await smart_cache.get("validation_result", quick_key)
            if quick_data:
                return quick_data
            
            # No está en caché rápido, hacer validación completa
            is_valid, session_data = await self.validate_session_token(session_token)
            
            if is_valid and session_data:
                quick_auth_data = {
                    "valid": True,
                    "user_id": session_data["user_id"],
                    "plan": session_data["user_data"].get("plan", "demo"),
                    "permissions": session_data["permissions"],
                    "plan_limits": session_data["plan_limits"],
                    "last_check": datetime.utcnow().isoformat()
                }
                
                # Guardar en caché rápido
                await smart_cache.set(
                    "validation_result",
                    quick_key,
                    quick_auth_data,
                    ttl=self.quick_check_ttl
                )
                
                return quick_auth_data
            else:
                return {"valid": False}
            
        except Exception as e:
            logger.error({
                "event": "quick_auth_check_error",
                "session_token": session_token,
                "error": str(e)
            })
            return {"valid": False, "error": str(e)}
    
    async def _cleanup_session(self, session_token: str, user_id: str):
        """Limpia una sesión específica."""
        try:
            # Eliminar datos de sesión
            session_key = f"session:{session_token}"
            await smart_cache.delete("auth_token", session_key)
            
            # Limpiar mapeo de usuario
            user_session_key = f"user_session:{user_id}"
            await smart_cache.delete("auth_token", user_session_key)
            
            # Limpiar caché rápido
            quick_key = f"quick_auth:{session_token}"
            await smart_cache.delete("validation_result", quick_key)
            
        except Exception as e:
            logger.error({
                "event": "session_cleanup_error",
                "session_token": session_token,
                "user_id": user_id,
                "error": str(e)
            })
    
    def _extract_permissions(self, user_data: Dict[str, Any]) -> List[str]:
        """Extrae permisos del usuario basado en su plan."""
        plan = user_data.get("plan", "demo")
        
        # Definir permisos por plan
        plan_permissions = {
            "demo": ["basic_chat", "basic_search"],
            "starter": ["basic_chat", "basic_search", "document_upload", "image_generation"],
            "professional": [
                "basic_chat", "basic_search", "document_upload", "image_generation",
                "voice_chat", "personal_agents", "priority_support"
            ],
            "enterprise": [
                "basic_chat", "basic_search", "document_upload", "image_generation",
                "voice_chat", "personal_agents", "priority_support", "api_access",
                "white_label", "custom_models"
            ]
        }
        
        return plan_permissions.get(plan, ["basic_chat"])
    
    def _extract_plan_limits(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extrae límites del plan del usuario."""
        from services.plans import PLAN_CONFIGS
        
        plan = user_data.get("plan", "demo")
        return PLAN_CONFIGS.get(plan, {}).get("limits", {})

# Instancia global del servicio
preauth_service = PreAuthService()