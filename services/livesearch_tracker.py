"""
Servicio de tracking para LiveSearch
Control de límites diarios por plan para mantener costos bajos
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import redis.asyncio as redis
from services.redis_service import get_redis_client
from services.plans import PLAN_CONFIGS
import json_log_formatter

# =============================================
# CONFIGURACIÓN DE LOGGING
# =============================================
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("livesearch_tracker")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

class LiveSearchTracker:
    """
    Servicio para rastrear y limitar el uso diario de LiveSearch
    Mantiene costos bajos con límites por plan
    """
    
    def __init__(self):
        self.redis_client = None
        
    async def get_redis(self) -> redis.Redis:
        """Obtiene cliente Redis."""
        if not self.redis_client:
            self.redis_client = await get_redis_client()
        return self.redis_client
    
    def _get_daily_key(self, user_id: str) -> str:
        """Genera clave Redis para uso diario."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        return f"livesearch_usage:{user_id}:{today}"
    
    def _get_plan_key(self, user_id: str) -> str:
        """Genera clave Redis para plan del usuario."""
        return f"user_plan:{user_id}"
    
    async def get_daily_usage(self, user_id: str) -> int:
        """
        Obtiene el uso diario actual de LiveSearch para un usuario
        
        Args:
            user_id: ID del usuario
            
        Returns:
            Número de búsquedas realizadas hoy
        """
        try:
            redis_client = await self.get_redis()
            key = self._get_daily_key(user_id)
            
            usage = await redis_client.get(key)
            current_usage = int(usage) if usage else 0
            
            logger.info({
                "event": "livesearch_usage_retrieved",
                "user_id": user_id,
                "current_usage": current_usage,
                "date": datetime.utcnow().strftime("%Y-%m-%d")
            })
            
            return current_usage
            
        except Exception as e:
            logger.error({
                "event": "livesearch_usage_error",
                "user_id": user_id,
                "error": str(e)
            })
            return 0
    
    async def get_user_plan(self, user_id: str) -> str:
        """
        Obtiene el plan del usuario desde Redis
        
        Args:
            user_id: ID del usuario
            
        Returns:
            Nombre del plan (demo, normal, pro, enterprise)
        """
        try:
            redis_client = await self.get_redis()
            key = self._get_plan_key(user_id)
            
            plan = await redis_client.get(key)
            user_plan = plan.decode('utf-8') if plan else "demo"
            
            # Validar que el plan existe
            if user_plan not in PLAN_CONFIGS:
                user_plan = "demo"
            
            logger.info({
                "event": "user_plan_retrieved",
                "user_id": user_id,
                "plan": user_plan
            })
            
            return user_plan
            
        except Exception as e:
            logger.error({
                "event": "user_plan_error",
                "user_id": user_id,
                "error": str(e)
            })
            return "demo"  # Plan por defecto en caso de error
    
    async def get_plan_limit(self, plan_name: str) -> int:
        """
        Obtiene el límite diario de LiveSearch para un plan
        
        Args:
            plan_name: Nombre del plan
            
        Returns:
            Límite diario (-1 para ilimitado)
        """
        try:
            if plan_name not in PLAN_CONFIGS:
                plan_name = "demo"
            
            limit = PLAN_CONFIGS[plan_name]["limits"]["max_live_search_daily"]
            
            logger.info({
                "event": "plan_limit_retrieved",
                "plan": plan_name,
                "daily_limit": limit
            })
            
            return limit
            
        except Exception as e:
            logger.error({
                "event": "plan_limit_error",
                "plan": plan_name,
                "error": str(e)
            })
            return 3  # Límite mínimo en caso de error
    
    async def can_use_livesearch(self, user_id: str) -> Dict[str, Any]:
        """
        Verifica si el usuario puede usar LiveSearch hoy
        
        Args:
            user_id: ID del usuario
            
        Returns:
            Dict con información de disponibilidad
        """
        try:
            # Obtener plan y límite
            user_plan = await self.get_user_plan(user_id)
            daily_limit = await self.get_plan_limit(user_plan)
            
            # Si es ilimitado (Enterprise)
            if daily_limit == -1:
                return {
                    "can_use": True,
                    "plan": user_plan,
                    "daily_limit": "unlimited",
                    "current_usage": 0,
                    "remaining": "unlimited",
                    "reason": "enterprise_unlimited"
                }
            
            # Obtener uso actual
            current_usage = await self.get_daily_usage(user_id)
            remaining = max(0, daily_limit - current_usage)
            can_use = current_usage < daily_limit
            
            result = {
                "can_use": can_use,
                "plan": user_plan,
                "daily_limit": daily_limit,
                "current_usage": current_usage,
                "remaining": remaining,
                "reason": "within_limit" if can_use else "limit_exceeded"
            }
            
            logger.info({
                "event": "livesearch_availability_checked",
                "user_id": user_id,
                "result": result
            })
            
            return result
            
        except Exception as e:
            logger.error({
                "event": "livesearch_availability_error",
                "user_id": user_id,
                "error": str(e)
            })
            return {
                "can_use": False,
                "plan": "demo",
                "daily_limit": 3,
                "current_usage": 0,
                "remaining": 0,
                "reason": "error_occurred"
            }
    
    async def increment_usage(self, user_id: str) -> Dict[str, Any]:
        """
        Incrementa el contador de uso diario
        
        Args:
            user_id: ID del usuario
            
        Returns:
            Dict con información del incremento
        """
        try:
            redis_client = await self.get_redis()
            key = self._get_daily_key(user_id)
            
            # Incrementar contador
            new_usage = await redis_client.incr(key)
            
            # Establecer TTL para que expire al final del día
            if new_usage == 1:  # Primera vez hoy
                # TTL hasta medianoche UTC
                tomorrow = datetime.utcnow().replace(
                    hour=0, minute=0, second=0, microsecond=0
                ) + timedelta(days=1)
                ttl_seconds = int((tomorrow - datetime.utcnow()).total_seconds())
                await redis_client.expire(key, ttl_seconds)
            
            # Obtener límite para comparar
            user_plan = await self.get_user_plan(user_id)
            daily_limit = await self.get_plan_limit(user_plan)
            
            result = {
                "usage_incremented": True,
                "new_usage": new_usage,
                "plan": user_plan,
                "daily_limit": daily_limit if daily_limit != -1 else "unlimited",
                "remaining": max(0, daily_limit - new_usage) if daily_limit != -1 else "unlimited"
            }
            
            logger.info({
                "event": "livesearch_usage_incremented",
                "user_id": user_id,
                "result": result
            })
            
            return result
            
        except Exception as e:
            logger.error({
                "event": "livesearch_increment_error",
                "user_id": user_id,
                "error": str(e)
            })
            return {
                "usage_incremented": False,
                "error": str(e)
            }
    
    async def reset_daily_usage(self, user_id: str) -> bool:
        """
        Resetea el uso diario (para testing o admin)
        
        Args:
            user_id: ID del usuario
            
        Returns:
            True si se reseteo correctamente
        """
        try:
            redis_client = await self.get_redis()
            key = self._get_daily_key(user_id)
            
            await redis_client.delete(key)
            
            logger.info({
                "event": "livesearch_usage_reset",
                "user_id": user_id
            })
            
            return True
            
        except Exception as e:
            logger.error({
                "event": "livesearch_reset_error",
                "user_id": user_id,
                "error": str(e)
            })
            return False
    
    async def set_user_plan(self, user_id: str, plan_name: str) -> bool:
        """
        Establece el plan del usuario en Redis
        
        Args:
            user_id: ID del usuario
            plan_name: Nombre del plan
            
        Returns:
            True si se estableció correctamente
        """
        try:
            if plan_name not in PLAN_CONFIGS:
                raise ValueError(f"Plan inválido: {plan_name}")
            
            redis_client = await self.get_redis()
            key = self._get_plan_key(user_id)
            
            await redis_client.set(key, plan_name, ex=86400 * 30)  # 30 días TTL
            
            logger.info({
                "event": "user_plan_set",
                "user_id": user_id,
                "plan": plan_name
            })
            
            return True
            
        except Exception as e:
            logger.error({
                "event": "user_plan_set_error",
                "user_id": user_id,
                "plan": plan_name,
                "error": str(e)
            })
            return False
    
    async def track_usage(
        self, 
        user_id: str, 
        search_query: str,
        auto_triggered: bool = False
    ) -> Dict[str, Any]:
        """
        🆕 NUEVO: Trackea el uso de LiveSearch con más contexto
        
        Args:
            user_id: ID del usuario
            search_query: Query de búsqueda realizada
            auto_triggered: True si fue auto-activado por incertidumbre IA
            
        Returns:
            Dict con información del tracking
        """
        try:
            # Verificar si puede usar LiveSearch
            availability = await self.can_use_livesearch(user_id)
            
            if not availability["can_use"]:
                logger.warning({
                    "event": "livesearch_limit_exceeded",
                    "user_id": user_id,
                    "plan": availability["plan"],
                    "daily_limit": availability["daily_limit"]
                })
                return {
                    "tracked": False,
                    "reason": "limit_exceeded",
                    "availability": availability
                }
            
            # Incrementar uso
            increment_result = await self.increment_usage(user_id)
            
            # Log detallado con contexto de auto-activación
            logger.info({
                "event": "livesearch_tracked",
                "user_id": user_id,
                "query": search_query[:100],  # Limitar longitud
                "auto_triggered": auto_triggered,
                "trigger_type": "auto" if auto_triggered else "manual",
                "new_usage": increment_result.get("new_usage", 0),
                "remaining": increment_result.get("remaining", 0)
            })
            
            return {
                "tracked": True,
                "auto_triggered": auto_triggered,
                "usage_info": increment_result
            }
            
        except Exception as e:
            logger.error({
                "event": "livesearch_tracking_error",
                "user_id": user_id,
                "error": str(e)
            })
            return {
                "tracked": False,
                "reason": "error",
                "error": str(e)
            }

# Instancia global del tracker
livesearch_tracker = LiveSearchTracker()