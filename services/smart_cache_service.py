"""
Smart Cache Service - Cache Inteligente con Predicción
Alias para CacheServiceEnterprise con funcionalidades adicionales
"""

import asyncio
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Importar el servicio enterprise existente
try:
    from services.cache_service_enterprise import (
        get_cache_service,
        CacheServiceEnterprise,
        generate_cache_key
    )
    CACHE_ENTERPRISE_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ CacheServiceEnterprise not available, using stub")
    CACHE_ENTERPRISE_AVAILABLE = False


class SmartCacheStub:
    """Stub para SmartCache cuando CacheServiceEnterprise no está disponible"""
    
    def __init__(self):
        self.cache: Dict[str, Any] = {}
        logger.info("SmartCacheStub initialized")
    
    async def get(self, key: str, default: Any = None) -> Any:
        """Obtiene valor del cache"""
        return self.cache.get(key, default)
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: int = 3600,
        tags: list = None
    ) -> bool:
        """Guarda valor en cache"""
        try:
            self.cache[key] = {
                "value": value,
                "expires_at": datetime.utcnow() + timedelta(seconds=ttl),
                "tags": tags or []
            }
            return True
        except Exception as e:
            logger.error(f"Error setting cache: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Elimina valor del cache"""
        try:
            if key in self.cache:
                del self.cache[key]
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting cache: {e}")
            return False
    
    async def clear_by_pattern(self, pattern: str) -> int:
        """Limpia cache por patrón"""
        try:
            deleted = 0
            keys_to_delete = [
                k for k in self.cache.keys() 
                if pattern in k
            ]
            
            for key in keys_to_delete:
                if await self.delete(key):
                    deleted += 1
            
            return deleted
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return 0
    
    async def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del cache"""
        # Limpiar expirados
        now = datetime.utcnow()
        expired_keys = [
            k for k, v in self.cache.items()
            if isinstance(v, dict) and v.get("expires_at", now) < now
        ]
        
        for key in expired_keys:
            del self.cache[key]
        
        return {
            "total_keys": len(self.cache),
            "memory_usage": "N/A (stub)",
            "hit_rate": "N/A (stub)",
            "status": "operational (stub)"
        }


class SmartCache:
    """
    Cache inteligente con predicción y optimización automática
    Wrapper sobre CacheServiceEnterprise
    """
    
    def __init__(self):
        if CACHE_ENTERPRISE_AVAILABLE:
            self.cache_service = get_cache_service()
            logger.info("SmartCache initialized with CacheServiceEnterprise")
        else:
            self.cache_service = SmartCacheStub()
            logger.info("SmartCache initialized with stub")
        
        self.access_patterns: Dict[str, int] = {}
        self.prediction_enabled = True
    
    async def get(self, key: str, default: Any = None) -> Any:
        """
        Obtiene valor del cache con tracking de acceso
        
        Args:
            key: Clave del cache
            default: Valor por defecto
        
        Returns:
            Valor del cache o default
        """
        try:
            # Tracking de patrones de acceso
            self.access_patterns[key] = self.access_patterns.get(key, 0) + 1
            
            if CACHE_ENTERPRISE_AVAILABLE:
                return await self.cache_service.get(key, default=default)
            else:
                return await self.cache_service.get(key, default)
                
        except Exception as e:
            logger.error(f"❌ Error getting from smart cache: {e}")
            return default
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: int = 3600,
        tags: list = None
    ) -> bool:
        """
        Guarda valor en cache con optimización automática
        
        Args:
            key: Clave del cache
            value: Valor a guardar
            ttl: Time to live en segundos
            tags: Tags para categorización
        
        Returns:
            True si se guardó correctamente
        """
        try:
            # Ajustar TTL basado en patrones de acceso
            if self.prediction_enabled:
                access_count = self.access_patterns.get(key, 0)
                if access_count > 10:
                    ttl = int(ttl * 1.5)  # Aumentar TTL para claves frecuentes
                elif access_count < 2:
                    ttl = int(ttl * 0.5)  # Reducir TTL para claves poco usadas
            
            if CACHE_ENTERPRISE_AVAILABLE:
                return await self.cache_service.set(
                    key=key,
                    value=value,
                    ttl=ttl,
                    tags=tags or []
                )
            else:
                return await self.cache_service.set(key, value, ttl, tags)
                
        except Exception as e:
            logger.error(f"❌ Error setting smart cache: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """
        Elimina valor del cache
        
        Args:
            key: Clave a eliminar
        
        Returns:
            True si se eliminó correctamente
        """
        try:
            # Limpiar tracking
            if key in self.access_patterns:
                del self.access_patterns[key]
            
            return await self.cache_service.delete(key)
            
        except Exception as e:
            logger.error(f"❌ Error deleting from smart cache: {e}")
            return False
    
    async def clear_by_pattern(self, pattern: str) -> int:
        """
        Limpia cache por patrón
        
        Args:
            pattern: Patrón a buscar
        
        Returns:
            Número de claves eliminadas
        """
        try:
            if CACHE_ENTERPRISE_AVAILABLE:
                # Usar método del enterprise
                return await self.cache_service.invalidate_by_pattern(pattern)
            else:
                return await self.cache_service.clear_by_pattern(pattern)
                
        except Exception as e:
            logger.error(f"❌ Error clearing cache by pattern: {e}")
            return 0
    
    async def get_or_set(
        self,
        key: str,
        factory: Callable,
        ttl: int = 3600,
        tags: list = None
    ) -> Any:
        """
        Obtiene del cache o ejecuta factory si no existe
        
        Args:
            key: Clave del cache
            factory: Función para generar el valor
            ttl: Time to live
            tags: Tags para categorización
        
        Returns:
            Valor del cache o generado
        """
        try:
            # Intentar obtener del cache
            value = await self.get(key)
            
            if value is not None:
                logger.debug(f"✅ Cache hit for key: {key}")
                return value
            
            # Si no existe, generar
            logger.debug(f"❌ Cache miss for key: {key}, generating...")
            
            if asyncio.iscoroutinefunction(factory):
                value = await factory()
            else:
                value = factory()
            
            # Guardar en cache
            await self.set(key, value, ttl, tags)
            
            return value
            
        except Exception as e:
            logger.error(f"❌ Error in get_or_set: {e}")
            # En caso de error, intentar generar el valor
            if asyncio.iscoroutinefunction(factory):
                return await factory()
            else:
                return factory()
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas del smart cache
        
        Returns:
            Diccionario con estadísticas
        """
        try:
            base_stats = await self.cache_service.get_stats()
            
            # Agregar estadísticas de acceso
            total_accesses = sum(self.access_patterns.values())
            most_accessed = sorted(
                self.access_patterns.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
            
            return {
                **base_stats,
                "smart_cache": {
                    "total_accesses": total_accesses,
                    "tracked_keys": len(self.access_patterns),
                    "most_accessed": [
                        {"key": k, "count": v} 
                        for k, v in most_accessed
                    ],
                    "prediction_enabled": self.prediction_enabled
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting smart cache stats: {e}")
            return {}
    
    async def optimize(self) -> Dict[str, Any]:
        """
        Optimiza el cache basado en patrones de acceso
        
        Returns:
            Resultados de la optimización
        """
        try:
            # Identificar claves poco usadas
            rarely_used = [
                k for k, v in self.access_patterns.items()
                if v < 2
            ]
            
            # Limpiar claves poco usadas
            deleted = 0
            for key in rarely_used:
                if await self.delete(key):
                    deleted += 1
            
            logger.info(f"✅ Optimized cache, deleted {deleted} rarely used keys")
            
            return {
                "status": "success",
                "keys_deleted": deleted,
                "keys_remaining": len(self.access_patterns)
            }
            
        except Exception as e:
            logger.error(f"❌ Error optimizing cache: {e}")
            return {
                "status": "error",
                "error": str(e)
            }


# Singleton instance
smart_cache = SmartCache()


# Funciones de conveniencia
async def get_smart_cache_stats() -> Dict[str, Any]:
    """Obtiene estadísticas del smart cache"""
    return await smart_cache.get_stats()


async def optimize_cache() -> Dict[str, Any]:
    """Optimiza el cache"""
    return await smart_cache.optimize()
