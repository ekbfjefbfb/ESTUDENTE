"""
Servicio Anti-Abuso v4.0 - Control ultra-optimizado de límites
Previene uso excesivo, protege márgenes y performance mejorado
Versión: 4.0 - Octubre 2025
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
import redis.asyncio as redis
from services.redis_service import get_redis_client
from services.plans import PLAN_CONFIGS
from services.smart_cache_service import smart_cache
import json_log_formatter

# =============================================
# CONFIGURACIÓN DE LOGGING
# =============================================
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("anti_abuse_service")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

class AntiAbuseService:
    """
    Servicio completo anti-abuso para prevenir uso excesivo
    Protege márgenes de ganancia y asegura sostenibilidad
    """
    
    def __init__(self):
        self.redis_client = None
        
    async def get_redis(self) -> redis.Redis:
        """Obtiene cliente Redis."""
        if not self.redis_client:
            self.redis_client = await get_redis_client()
        return self.redis_client
    
    def _get_usage_key(self, user_id: str, metric: str, timeframe: str = "daily") -> str:
        """Genera clave Redis para tracking de uso."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if timeframe == "daily":
            return f"usage:{user_id}:{metric}:{today}"
        elif timeframe == "minute":
            minute = datetime.utcnow().strftime("%Y-%m-%d:%H:%M")
            return f"usage:{user_id}:{metric}:{minute}"
        return f"usage:{user_id}:{metric}"
    
    def _get_cooldown_key(self, user_id: str) -> str:
        """Genera clave Redis para cooldown."""
        return f"cooldown:{user_id}"
    
    def _get_plan_key(self, user_id: str) -> str:
        """Genera clave Redis para plan del usuario."""
        return f"user_plan:{user_id}"
    
    async def get_user_plan(self, user_id: str) -> str:
        """Obtiene el plan del usuario con caché inteligente."""
        try:
            # Intentar obtener del caché primero
            async def fetch_plan():
                redis_client = await self.get_redis()
                key = self._get_plan_key(user_id)
                
                plan = await redis_client.get(key)
                user_plan = plan.decode('utf-8') if plan else "demo"
                
                if user_plan not in PLAN_CONFIGS:
                    user_plan = "demo"
                
                return user_plan
            
            # Usar caché inteligente
            user_plan = await smart_cache.get_or_set(
                "user_plan", 
                user_id, 
                fetch_plan,
                ttl=600  # 10 minutos
            )
            
            return user_plan
            
        except Exception as e:
            logger.error({
                "event": "get_user_plan_error",
                "user_id": user_id,
                "error": str(e)
            })
            return "demo"
    
    async def check_rate_limit(self, user_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Verifica límite de requests por minuto con caché optimizado
        
        Returns:
            Tuple[bool, dict]: (can_proceed, info)
        """
        try:
            # Obtener plan del usuario (ya optimizado con caché)
            user_plan = await self.get_user_plan(user_id)
            
            # Obtener límites del plan desde caché
            async def fetch_plan_limits():
                return PLAN_CONFIGS[user_plan]["limits"]
            
            plan_limits = await smart_cache.get_or_set(
                "plan_limits",
                user_plan,
                fetch_plan_limits,
                ttl=3600  # 1 hora - los límites cambian poco
            )
            
            # Verificar cooldown entre requests
            if "cooldown_between_requests" in plan_limits:
                cooldown_seconds = plan_limits["cooldown_between_requests"]
                if cooldown_seconds > 0:
                    redis_client = await self.get_redis()
                    cooldown_key = self._get_cooldown_key(user_id)
                    
                    if await redis_client.exists(cooldown_key):
                        return False, {
                            "blocked": True,
                            "reason": "cooldown_active",
                            "cooldown_seconds": cooldown_seconds,
                            "plan": user_plan
                        }
                    
                    # Establecer cooldown
                    await redis_client.setex(cooldown_key, cooldown_seconds, "1")
            
            # Verificar límite por minuto
            redis_client = await self.get_redis()
            minute_key = self._get_usage_key(user_id, "requests", "minute")
            current_minute_usage = await redis_client.get(minute_key)
            current_minute_usage = int(current_minute_usage) if current_minute_usage else 0
            
            max_per_minute = plan_limits.get("max_requests_per_minute", 10)
            
            if current_minute_usage >= max_per_minute:
                return False, {
                    "blocked": True,
                    "reason": "rate_limit_exceeded",
                    "current_usage": current_minute_usage,
                    "limit": max_per_minute,
                    "plan": user_plan
                }
            
            # Incrementar contador del minuto
            await redis_client.incr(minute_key)
            await redis_client.expire(minute_key, 60)  # Expira en 1 minuto
            
            # Cachear estado del rate limit por poco tiempo
            rate_limit_status = {
                "blocked": False,
                "current_usage": current_minute_usage + 1,
                "limit": max_per_minute,
                "plan": user_plan
            }
            
            await smart_cache.set(
                "rate_limit_status",
                f"{user_id}:minute",
                rate_limit_status,
                ttl=10  # 10 segundos
            )
            
            return True, rate_limit_status
            
        except Exception as e:
            logger.error({
                "event": "rate_limit_check_error",
                "user_id": user_id,
                "error": str(e)
            })
            return False, {"blocked": True, "reason": "error", "error": str(e)}
    
    async def check_daily_limit(self, user_id: str, metric: str, increment: int = 1) -> Tuple[bool, Dict[str, Any]]:
        """
        Verifica y actualiza límites diarios
        
        Args:
            user_id: ID del usuario
            metric: Métrica a verificar (requests, tokens, images, etc.)
            increment: Cantidad a incrementar
            
        Returns:
            Tuple[bool, dict]: (can_proceed, info)
        """
        try:
            user_plan = await self.get_user_plan(user_id)
            plan_limits = PLAN_CONFIGS[user_plan]["limits"]
            
            limit_key = f"max_{metric}_daily"
            max_daily = plan_limits.get(limit_key, 0)
            
            # Si es ilimitado (-1), permitir
            if max_daily == -1:
                return True, {
                    "allowed": True,
                    "reason": "unlimited",
                    "plan": user_plan,
                    "limit": "unlimited"
                }
            
            redis_client = await self.get_redis()
            daily_key = self._get_usage_key(user_id, metric, "daily")
            current_usage = await redis_client.get(daily_key)
            current_usage = int(current_usage) if current_usage else 0
            
            # Verificar si excedería el límite
            if current_usage + increment > max_daily:
                return False, {
                    "allowed": False,
                    "reason": "daily_limit_exceeded",
                    "current_usage": current_usage,
                    "increment": increment,
                    "limit": max_daily,
                    "plan": user_plan
                }
            
            # Incrementar uso
            new_usage = await redis_client.incrby(daily_key, increment)
            
            # Establecer TTL para que expire al final del día
            if new_usage == increment:  # Primera vez hoy
                tomorrow = datetime.utcnow().replace(
                    hour=0, minute=0, second=0, microsecond=0
                ) + timedelta(days=1)
                ttl_seconds = int((tomorrow - datetime.utcnow()).total_seconds())
                await redis_client.expire(daily_key, ttl_seconds)
            
            return True, {
                "allowed": True,
                "current_usage": new_usage,
                "limit": max_daily,
                "remaining": max_daily - new_usage,
                "plan": user_plan
            }
            
        except Exception as e:
            logger.error({
                "event": "daily_limit_check_error",
                "user_id": user_id,
                "metric": metric,
                "error": str(e)
            })
            return False, {"allowed": False, "reason": "error", "error": str(e)}
    
    async def check_request_limits(self, user_id: str, tokens: int = 0) -> Tuple[bool, Dict[str, Any]]:
        """
        Verificación completa para un request
        
        Args:
            user_id: ID del usuario
            tokens: Número de tokens del request
            
        Returns:
            Tuple[bool, dict]: (can_proceed, combined_info)
        """
        try:
            # 1. Verificar rate limiting
            rate_ok, rate_info = await self.check_rate_limit(user_id)
            if not rate_ok:
                logger.warning({
                    "event": "request_blocked_rate_limit",
                    "user_id": user_id,
                    "info": rate_info
                })
                return False, rate_info
            
            # 2. Verificar límite diario de requests
            requests_ok, requests_info = await self.check_daily_limit(user_id, "requests", 1)
            if not requests_ok:
                logger.warning({
                    "event": "request_blocked_daily_requests",
                    "user_id": user_id,
                    "info": requests_info
                })
                return False, requests_info
            
            # 3. Verificar límite diario de tokens si se especifica
            if tokens > 0:
                tokens_ok, tokens_info = await self.check_daily_limit(user_id, "tokens", tokens)
                if not tokens_ok:
                    logger.warning({
                        "event": "request_blocked_daily_tokens",
                        "user_id": user_id,
                        "tokens": tokens,
                        "info": tokens_info
                    })
                    return False, tokens_info
            
            # Todo OK
            combined_info = {
                "allowed": True,
                "rate_limit": rate_info,
                "daily_requests": requests_info,
                "daily_tokens": tokens_info if tokens > 0 else None
            }
            
            logger.info({
                "event": "request_allowed",
                "user_id": user_id,
                "tokens": tokens,
                "info": combined_info
            })
            
            return True, combined_info
            
        except Exception as e:
            logger.error({
                "event": "request_limits_check_error",
                "user_id": user_id,
                "error": str(e)
            })
            return False, {"allowed": False, "reason": "error", "error": str(e)}
    
    async def check_resource_limits(self, user_id: str, resource_type: str, amount: int = 1) -> Tuple[bool, Dict[str, Any]]:
        """
        Verifica límites para recursos específicos (imágenes, voz, documentos)
        
        Args:
            user_id: ID del usuario
            resource_type: Tipo de recurso (images, voice_minutes, document_mb)
            amount: Cantidad a usar
            
        Returns:
            Tuple[bool, dict]: (can_proceed, info)
        """
        try:
            return await self.check_daily_limit(user_id, resource_type, amount)
            
        except Exception as e:
            logger.error({
                "event": "resource_limits_check_error",
                "user_id": user_id,
                "resource_type": resource_type,
                "error": str(e)
            })
            return False, {"allowed": False, "reason": "error", "error": str(e)}
    
    async def get_usage_summary(self, user_id: str) -> Dict[str, Any]:
        """
        Obtiene resumen completo de uso del usuario
        
        Returns:
            Dict con información de uso y límites
        """
        try:
            user_plan = await self.get_user_plan(user_id)
            plan_limits = PLAN_CONFIGS[user_plan]["limits"]
            
            redis_client = await self.get_redis()
            today = datetime.utcnow().strftime("%Y-%m-%d")
            
            # Métricas a consultar
            metrics = ["requests", "tokens", "images", "voice_minutes", "document_mb"]
            usage_data = {}
            
            for metric in metrics:
                daily_key = self._get_usage_key(user_id, metric, "daily")
                current_usage = await redis_client.get(daily_key)
                current_usage = int(current_usage) if current_usage else 0
                
                limit_key = f"max_{metric}_daily"
                daily_limit = plan_limits.get(limit_key, 0)
                
                usage_data[metric] = {
                    "current_usage": current_usage,
                    "daily_limit": daily_limit if daily_limit != -1 else "unlimited",
                    "remaining": max(0, daily_limit - current_usage) if daily_limit != -1 else "unlimited"
                }
            
            return {
                "user_id": user_id,
                "plan": user_plan,
                "date": today,
                "usage": usage_data,
                "plan_info": {
                    "name": PLAN_CONFIGS[user_plan]["name"],
                    "price": PLAN_CONFIGS[user_plan]["price"]
                }
            }
            
        except Exception as e:
            logger.error({
                "event": "usage_summary_error",
                "user_id": user_id,
                "error": str(e)
            })
            return {"error": str(e)}
    
    async def reset_user_usage(self, user_id: str, metric: str = "all") -> bool:
        """
        Resetea el uso de un usuario (admin/testing)
        
        Args:
            user_id: ID del usuario
            metric: Métrica específica o "all" para todas
            
        Returns:
            True si se reseteó correctamente
        """
        try:
            redis_client = await self.get_redis()
            today = datetime.utcnow().strftime("%Y-%m-%d")
            
            if metric == "all":
                metrics = ["requests", "tokens", "images", "voice_minutes", "document_mb", "livesearch"]
            else:
                metrics = [metric]
            
            for m in metrics:
                daily_key = self._get_usage_key(user_id, m, "daily")
                await redis_client.delete(daily_key)
            
            # También resetear cooldown
            cooldown_key = self._get_cooldown_key(user_id)
            await redis_client.delete(cooldown_key)
            
            logger.info({
                "event": "user_usage_reset",
                "user_id": user_id,
                "metric": metric
            })
            
            return True
            
        except Exception as e:
            logger.error({
                "event": "reset_usage_error",
                "user_id": user_id,
                "metric": metric,
                "error": str(e)
            })
            return False
    
    async def check_demo_total_limits(self, user_id: str) -> dict:
        """Verifica límites totales para usuarios demo (3 días, límites ultra restrictivos)"""
        from .plans import get_demo_usage_limits
        
        redis = await self.get_redis()
        demo_limits = get_demo_usage_limits()
        
        # Verificar si el usuario demo ha excedido la duración (3 días)
        demo_key = f"demo_start:{user_id}"
        demo_start = await redis.get(demo_key)
        
        if demo_start:
            start_time = datetime.fromisoformat(demo_start.decode())
            if (datetime.now() - start_time).total_seconds() > demo_limits["duration_hours"] * 3600:
                return {
                    "allowed": False,
                    "reason": "Demo period expired (3 days)",
                    "retry_after": None
                }
        else:
            # Primera vez, registrar inicio del periodo demo
            await redis.setex(
                demo_key,
                demo_limits["duration_hours"] * 3600,  # 72 horas
                datetime.now().isoformat()
            )
        
        # Verificar límites totales
        total_checks = [
            ("requests", demo_limits["max_requests_total"]),
            ("tokens", demo_limits["max_tokens_total"]),
            ("images", demo_limits["max_images_total"]),
            ("voice_minutes", demo_limits["max_voice_minutes_total"]),
            ("document_mb", demo_limits["max_document_mb_total"]),
            ("livesearch", demo_limits["max_livesearch_total"])
        ]
        
        for resource, max_total in total_checks.items():
            total_key = f"demo_total:{user_id}:{resource}"
            current_total = await redis.get(total_key)
            current_total = int(current_total.decode()) if current_total else 0
            
            if current_total >= max_total:
                return {
                    "allowed": False,
                    "reason": f"Demo {resource} limit exceeded ({current_total}/{max_total})",
                    "retry_after": None
                }
        
        return {"allowed": True}
    
    async def increment_demo_usage(self, user_id: str, resource: str, amount: int = 1) -> None:
        """Incrementa el uso total de un recurso para usuario demo"""
        redis = await self.get_redis()
        total_key = f"demo_total:{user_id}:{resource}"
        
        # Incrementar contador con expiración de 3 días
        await redis.incr(total_key, amount)
        await redis.expire(total_key, 72 * 3600)  # 3 días

# Instancia global del servicio
anti_abuse_service = AntiAbuseService()