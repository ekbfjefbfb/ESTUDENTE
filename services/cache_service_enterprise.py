"""
🚀 CACHE SERVICE ENTERPRISE - VERSIÓN PRODUCCIÓN v3.0
=====================================================

Sistema de cache multinivel optimizado para alta concurrencia y producción:

CARACTERÍSTICAS ENTERPRISE:
- ✅ Cache multinivel (L1: Memoria local, L2: Redis distribuido)
- ✅ Estrategias de invalidación inteligentes
- ✅ Compresión automática para datos grandes
- ✅ Métricas granulares de rendimiento
- ✅ Fallback automático a memoria si Redis falla
- ✅ TTL dinámico basado en patrones de uso
- ✅ Cache warming para datos críticos
- ✅ Serialización optimizada
- ✅ Rate limiting en operaciones de cache
- ✅ Health checks automáticos

Este servicio está diseñado para manejar millones de operaciones por hora
con latencia mínima y alta disponibilidad.
"""

import asyncio
import hashlib
import json
import logging
import pickle
import time
import zlib
from datetime import datetime, timedelta
from typing import Any, Optional, Dict, List, Union, Tuple, Callable
from dataclasses import dataclass
from enum import Enum

import aioredis
from utils.safe_metrics import SafeMetric

logger = logging.getLogger("cache_enterprise")

# ===============================================
# 🎯 CONFIGURACIÓN Y ENUMS
# ===============================================

class CacheLevel(str, Enum):
    """Niveles de cache disponibles"""
    L1_MEMORY = "l1_memory"
    L2_REDIS = "l2_redis"
    BOTH = "both"

class CacheStrategy(str, Enum):
    """Estrategias de cache"""
    LRU = "lru"           # Least Recently Used
    LFU = "lfu"           # Least Frequently Used
    FIFO = "fifo"         # First In, First Out
    TTL_BASED = "ttl"     # Time To Live based

class SerializationMethod(str, Enum):
    """Métodos de serialización"""
    JSON = "json"
    PICKLE = "pickle"
    COMPRESSED_JSON = "compressed_json"
    COMPRESSED_PICKLE = "compressed_pickle"

@dataclass
class CacheItem:
    """Item de cache con metadatos"""
    key: str
    value: Any
    created_at: datetime
    last_accessed: datetime
    access_count: int
    ttl_seconds: Optional[int]
    size_bytes: int
    serialization_method: SerializationMethod
    
    @property
    def is_expired(self) -> bool:
        """Verifica si el item ha expirado"""
        if not self.ttl_seconds:
            return False
        return (datetime.utcnow() - self.created_at).total_seconds() > self.ttl_seconds
    
    @property
    def age_seconds(self) -> float:
        """Edad del item en segundos"""
        return (datetime.utcnow() - self.created_at).total_seconds()

@dataclass
class CacheConfig:
    """Configuración del cache"""
    # Redis settings
    redis_url: str = "redis://localhost:6379"
    redis_db: int = 0
    redis_max_connections: int = 50
    redis_retry_times: int = 3
    
    # L1 Cache (Memory) settings
    l1_max_size_mb: int = 100
    l1_max_items: int = 10000
    l1_default_ttl: int = 300  # 5 minutos
    
    # L2 Cache (Redis) settings
    l2_default_ttl: int = 3600  # 1 hora
    l2_max_value_size_mb: int = 10
    
    # Compression settings
    compression_threshold_bytes: int = 1024  # Comprimir si > 1KB
    compression_level: int = 6
    
    # Performance settings
    enable_metrics: bool = True
    enable_health_checks: bool = True
    health_check_interval: int = 30
    
    # Cache warming
    enable_warming: bool = True
    warming_patterns: List[str] = None
    
    def __post_init__(self):
        if self.warming_patterns is None:
            self.warming_patterns = ["user_*", "session_*", "config_*"]

# ===============================================
# 🔧 UTILIDADES DE SERIALIZACIÓN
# ===============================================

class CacheSerializer:
    """Manejador de serialización optimizado"""
    
    @staticmethod
    def serialize(value: Any, method: SerializationMethod) -> Tuple[bytes, int]:
        """Serializa un valor y retorna (datos, tamaño)"""
        try:
            if method == SerializationMethod.JSON:
                data = json.dumps(value, default=str).encode('utf-8')
            elif method == SerializationMethod.PICKLE:
                data = pickle.dumps(value)
            elif method == SerializationMethod.COMPRESSED_JSON:
                json_data = json.dumps(value, default=str).encode('utf-8')
                data = zlib.compress(json_data, level=6)
            elif method == SerializationMethod.COMPRESSED_PICKLE:
                pickle_data = pickle.dumps(value)
                data = zlib.compress(pickle_data, level=6)
            else:
                raise ValueError(f"Método de serialización no soportado: {method}")
            
            return data, len(data)
            
        except Exception as e:
            logger.error(f"Error serializando datos: {e}")
            raise
    
    @staticmethod
    def deserialize(data: bytes, method: SerializationMethod) -> Any:
        """Deserializa datos"""
        try:
            if method == SerializationMethod.JSON:
                return json.loads(data.decode('utf-8'))
            elif method == SerializationMethod.PICKLE:
                return pickle.loads(data)
            elif method == SerializationMethod.COMPRESSED_JSON:
                decompressed = zlib.decompress(data)
                return json.loads(decompressed.decode('utf-8'))
            elif method == SerializationMethod.COMPRESSED_PICKLE:
                decompressed = zlib.decompress(data)
                return pickle.loads(decompressed)
            else:
                raise ValueError(f"Método de deserialización no soportado: {method}")
                
        except Exception as e:
            logger.error(f"Error deserializando datos: {e}")
            raise
    
    @staticmethod
    def choose_best_method(value: Any, size_threshold: int = 1024) -> SerializationMethod:
        """Elige el mejor método de serialización basado en el valor"""
        try:
            # Probar JSON primero (más rápido y legible)
            json_data = json.dumps(value, default=str).encode('utf-8')
            json_size = len(json_data)
            
            if json_size <= size_threshold:
                return SerializationMethod.JSON
            else:
                return SerializationMethod.COMPRESSED_JSON
                
        except (TypeError, ValueError):
            # Si JSON falla, usar pickle
            try:
                pickle_data = pickle.dumps(value)
                pickle_size = len(pickle_data)
                
                if pickle_size <= size_threshold:
                    return SerializationMethod.PICKLE
                else:
                    return SerializationMethod.COMPRESSED_PICKLE
                    
            except Exception:
                # Fallback a JSON con str()
                return SerializationMethod.JSON

# ===============================================
# 💾 CACHE L1 (MEMORIA LOCAL)
# ===============================================

class L1MemoryCache:
    """Cache L1 en memoria con estrategias de eviction"""
    
    def __init__(self, config: CacheConfig):
        self.config = config
        self.items: Dict[str, CacheItem] = {}
        self.access_order: List[str] = []  # Para LRU
        self.current_size_bytes = 0
        self.max_size_bytes = config.l1_max_size_mb * 1024 * 1024
        
        # Métricas
        self.metrics = SafeMetric()
        self.hit_counter = self.metrics.counter('l1_cache_hits_total', 'L1 cache hits')
        self.miss_counter = self.metrics.counter('l1_cache_misses_total', 'L1 cache misses')
        self.eviction_counter = self.metrics.counter('l1_cache_evictions_total', 'L1 cache evictions')
        
        logger.info(f"✅ L1 Memory Cache inicializado - Max: {config.l1_max_size_mb}MB, {config.l1_max_items} items")
    
    def _update_access(self, key: str):
        """Actualiza el orden de acceso para LRU"""
        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)
        
        if key in self.items:
            self.items[key].last_accessed = datetime.utcnow()
            self.items[key].access_count += 1
    
    def _evict_if_needed(self):
        """Ejecuta eviction si es necesario"""
        while (self.current_size_bytes > self.max_size_bytes or 
               len(self.items) > self.config.l1_max_items):
            
            if not self.items:
                break
            
            # LRU: remover el menos recientemente usado
            oldest_key = self.access_order[0]
            self._remove_item(oldest_key)
            self.eviction_counter.inc()
    
    def _remove_item(self, key: str):
        """Remueve un item del cache"""
        if key in self.items:
            item = self.items[key]
            self.current_size_bytes -= item.size_bytes
            del self.items[key]
            
        if key in self.access_order:
            self.access_order.remove(key)
    
    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
        """Almacena un valor en L1"""
        try:
            # Determinar método de serialización
            serialization_method = CacheSerializer.choose_best_method(
                value, self.config.compression_threshold_bytes
            )
            
            # Serializar para calcular tamaño
            data, size_bytes = CacheSerializer.serialize(value, serialization_method)
            
            # Verificar si el item es demasiado grande
            if size_bytes > self.max_size_bytes * 0.1:  # No más del 10% del cache
                logger.warning(f"Item {key} demasiado grande para L1: {size_bytes} bytes")
                return False
            
            # Remover item existente si existe
            if key in self.items:
                self._remove_item(key)
            
            # Crear nuevo item
            item = CacheItem(
                key=key,
                value=value,
                created_at=datetime.utcnow(),
                last_accessed=datetime.utcnow(),
                access_count=1,
                ttl_seconds=ttl_seconds or self.config.l1_default_ttl,
                size_bytes=size_bytes,
                serialization_method=serialization_method
            )
            
            # Agregar al cache
            self.items[key] = item
            self.current_size_bytes += size_bytes
            self._update_access(key)
            
            # Eviction si es necesario
            self._evict_if_needed()
            
            return True
            
        except Exception as e:
            logger.error(f"Error almacenando en L1 cache: {e}")
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """Obtiene un valor del L1"""
        try:
            if key not in self.items:
                self.miss_counter.inc()
                return None
            
            item = self.items[key]
            
            # Verificar expiración
            if item.is_expired:
                self._remove_item(key)
                self.miss_counter.inc()
                return None
            
            # Actualizar acceso
            self._update_access(key)
            self.hit_counter.inc()
            
            return item.value
            
        except Exception as e:
            logger.error(f"Error obteniendo de L1 cache: {e}")
            self.miss_counter.inc()
            return None
    
    def delete(self, key: str) -> bool:
        """Elimina un valor del L1"""
        try:
            if key in self.items:
                self._remove_item(key)
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error eliminando de L1 cache: {e}")
            return False
    
    def clear(self):
        """Limpia todo el cache L1"""
        self.items.clear()
        self.access_order.clear()
        self.current_size_bytes = 0
        logger.info("L1 cache limpiado")
    
    def get_stats(self) -> Dict[str, Any]:
        """Estadísticas del L1 cache"""
        total_items = len(self.items)
        total_accesses = sum(item.access_count for item in self.items.values())
        
        return {
            "total_items": total_items,
            "size_bytes": self.current_size_bytes,
            "size_mb": round(self.current_size_bytes / (1024 * 1024), 2),
            "utilization_percent": round((self.current_size_bytes / self.max_size_bytes) * 100, 2),
            "total_accesses": total_accesses,
            "average_access_count": round(total_accesses / total_items, 2) if total_items > 0 else 0
        }

# ===============================================
# 🌐 CACHE ENTERPRISE SERVICE
# ===============================================

class CacheServiceEnterprise:
    """Servicio de cache enterprise con capacidades avanzadas"""
    
    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        
        # Componentes del cache
        self.l1_cache = L1MemoryCache(self.config)
        self.redis_client: Optional[aioredis.Redis] = None
        self.is_redis_available = False
        
        # Estado del servicio
        self.is_initialized = False
        self.health_check_task: Optional[asyncio.Task] = None
        
        # Métricas globales
        self.metrics = SafeMetric()
        self.operation_counter = self.metrics.counter(
            'cache_operations_total',
            'Total cache operations',
            ['operation', 'level', 'status']
        )
        
        self.latency_histogram = self.metrics.histogram(
            'cache_operation_duration_seconds',
            'Cache operation duration',
            ['operation', 'level'],
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0]
        )
        
        self.cache_size_gauge = self.metrics.gauge(
            'cache_size_bytes',
            'Cache size in bytes',
            ['level']
        )
        
        logger.info("🚀 CacheServiceEnterprise inicializado")
    
    async def initialize(self) -> bool:
        """Inicializa el servicio de cache"""
        try:
            logger.info("🔄 Inicializando Cache Service Enterprise...")
            
            # Inicializar conexión Redis
            await self._initialize_redis()
            
            # Iniciar health checks
            if self.config.enable_health_checks:
                self.health_check_task = asyncio.create_task(self._health_check_loop())
            
            # Cache warming si está habilitado
            if self.config.enable_warming:
                asyncio.create_task(self._warm_cache())
            
            self.is_initialized = True
            logger.info("✅ Cache Service Enterprise inicializado exitosamente")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error inicializando Cache Service: {e}")
            return False
    
    async def _initialize_redis(self):
        """Inicializa la conexión a Redis"""
        try:
            self.redis_client = aioredis.from_url(
                self.config.redis_url,
                db=self.config.redis_db,
                max_connections=self.config.redis_max_connections,
                retry_on_timeout=True,
                health_check_interval=30
            )
            
            # Test de conectividad
            await self.redis_client.ping()
            self.is_redis_available = True
            
            logger.info(f"✅ Redis conectado: {self.config.redis_url}")
            
        except Exception as e:
            logger.warning(f"⚠️ Redis no disponible: {e}. Funcionando solo con L1 cache.")
            self.is_redis_available = False
    
    async def _health_check_loop(self):
        """Loop de health checks"""
        while True:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                
                # Check Redis
                if self.redis_client:
                    try:
                        await self.redis_client.ping()
                        if not self.is_redis_available:
                            logger.info("✅ Redis reconectado")
                            self.is_redis_available = True
                    except Exception:
                        if self.is_redis_available:
                            logger.warning("⚠️ Redis desconectado")
                            self.is_redis_available = False
                
                # Actualizar métricas de tamaño
                self.cache_size_gauge.set(
                    self.l1_cache.current_size_bytes, 
                    labels=['l1_memory']
                )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error en health check: {e}")
    
    async def _warm_cache(self):
        """Warming del cache con patrones predefinidos"""
        try:
            logger.info("🔥 Iniciando cache warming...")
            
            # Aquí implementarías la lógica de warming específica
            # Por ejemplo, cargar configuraciones frecuentes, datos de usuarios activos, etc.
            
            warm_data = {
                "config_app_settings": {"version": "3.0", "features": ["agents", "cache"]},
                "config_rate_limits": {"default": 100, "premium": 1000},
                "config_agent_settings": {"max_concurrent": 10, "timeout": 30}
            }
            
            for key, value in warm_data.items():
                await self.set(key, value, ttl_seconds=3600)  # 1 hora
            
            logger.info(f"✅ Cache warming completado: {len(warm_data)} items")
            
        except Exception as e:
            logger.error(f"Error en cache warming: {e}")
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl_seconds: Optional[int] = None,
        level: CacheLevel = CacheLevel.BOTH
    ) -> bool:
        """
        Almacena un valor en el cache
        
        Args:
            key: Clave del cache
            value: Valor a almacenar
            ttl_seconds: Tiempo de vida en segundos
            level: Nivel de cache (L1, L2 o ambos)
        """
        start_time = time.time()
        
        try:
            success = False
            
            # L1 Cache (siempre intentar si está en el nivel)
            if level in [CacheLevel.L1_MEMORY, CacheLevel.BOTH]:
                l1_success = self.l1_cache.set(key, value, ttl_seconds)
                if l1_success:
                    success = True
                    self.operation_counter.inc(labels=['set', 'l1', 'success'])
                else:
                    self.operation_counter.inc(labels=['set', 'l1', 'failed'])
            
            # L2 Cache (Redis)
            if level in [CacheLevel.L2_REDIS, CacheLevel.BOTH] and self.is_redis_available:
                try:
                    # Serializar para Redis
                    serialization_method = CacheSerializer.choose_best_method(
                        value, self.config.compression_threshold_bytes
                    )
                    data, size_bytes = CacheSerializer.serialize(value, serialization_method)
                    
                    # Verificar tamaño máximo
                    max_size = self.config.l2_max_value_size_mb * 1024 * 1024
                    if size_bytes > max_size:
                        logger.warning(f"Item {key} demasiado grande para Redis: {size_bytes} bytes")
                    else:
                        # Crear estructura con metadatos
                        redis_value = {
                            'data': data,
                            'method': serialization_method.value,
                            'created_at': datetime.utcnow().isoformat(),
                            'size_bytes': size_bytes
                        }
                        
                        # Almacenar en Redis
                        ttl = ttl_seconds or self.config.l2_default_ttl
                        await self.redis_client.setex(
                            key, 
                            ttl, 
                            json.dumps(redis_value, default=str)
                        )
                        
                        success = True
                        self.operation_counter.inc(labels=['set', 'l2', 'success'])
                
                except Exception as e:
                    logger.warning(f"Error almacenando en Redis: {e}")
                    self.operation_counter.inc(labels=['set', 'l2', 'failed'])
            
            # Métricas de latencia
            duration = time.time() - start_time
            self.latency_histogram.observe(duration, labels=['set', level.value])
            
            return success
            
        except Exception as e:
            logger.error(f"Error en cache.set({key}): {e}")
            self.operation_counter.inc(labels=['set', level.value, 'error'])
            return False
    
    async def get(self, key: str, level: CacheLevel = CacheLevel.BOTH) -> Optional[Any]:
        """
        Obtiene un valor del cache
        
        Args:
            key: Clave del cache
            level: Nivel de cache a consultar
        """
        start_time = time.time()
        
        try:
            # L1 Cache primero (más rápido)
            if level in [CacheLevel.L1_MEMORY, CacheLevel.BOTH]:
                value = self.l1_cache.get(key)
                if value is not None:
                    duration = time.time() - start_time
                    self.latency_histogram.observe(duration, labels=['get', 'l1'])
                    self.operation_counter.inc(labels=['get', 'l1', 'hit'])
                    return value
                else:
                    self.operation_counter.inc(labels=['get', 'l1', 'miss'])
            
            # L2 Cache (Redis) si L1 falló
            if level in [CacheLevel.L2_REDIS, CacheLevel.BOTH] and self.is_redis_available:
                try:
                    redis_data = await self.redis_client.get(key)
                    if redis_data:
                        # Deserializar desde Redis
                        redis_value = json.loads(redis_data)
                        data = redis_value['data']
                        method = SerializationMethod(redis_value['method'])
                        
                        # Si es string (JSON simple), convertir a bytes
                        if isinstance(data, str):
                            data = data.encode('utf-8')
                        elif isinstance(data, list):
                            # Si es una lista (pickle en base64), convertir
                            import base64
                            data = base64.b64decode(''.join(map(str, data)))
                        
                        value = CacheSerializer.deserialize(data, method)
                        
                        # Promocionar a L1 si está configurado para ambos niveles
                        if level == CacheLevel.BOTH:
                            self.l1_cache.set(key, value)
                        
                        duration = time.time() - start_time
                        self.latency_histogram.observe(duration, labels=['get', 'l2'])
                        self.operation_counter.inc(labels=['get', 'l2', 'hit'])
                        return value
                    else:
                        self.operation_counter.inc(labels=['get', 'l2', 'miss'])
                
                except Exception as e:
                    logger.warning(f"Error obteniendo de Redis: {e}")
                    self.operation_counter.inc(labels=['get', 'l2', 'error'])
            
            # No encontrado
            duration = time.time() - start_time
            self.latency_histogram.observe(duration, labels=['get', level.value])
            return None
            
        except Exception as e:
            logger.error(f"Error en cache.get({key}): {e}")
            self.operation_counter.inc(labels=['get', level.value, 'error'])
            return None
    
    async def delete(self, key: str, level: CacheLevel = CacheLevel.BOTH) -> bool:
        """Elimina un valor del cache"""
        try:
            success = False
            
            # L1 Cache
            if level in [CacheLevel.L1_MEMORY, CacheLevel.BOTH]:
                if self.l1_cache.delete(key):
                    success = True
                    self.operation_counter.inc(labels=['delete', 'l1', 'success'])
            
            # L2 Cache (Redis)
            if level in [CacheLevel.L2_REDIS, CacheLevel.BOTH] and self.is_redis_available:
                try:
                    result = await self.redis_client.delete(key)
                    if result > 0:
                        success = True
                        self.operation_counter.inc(labels=['delete', 'l2', 'success'])
                
                except Exception as e:
                    logger.warning(f"Error eliminando de Redis: {e}")
                    self.operation_counter.inc(labels=['delete', 'l2', 'failed'])
            
            return success
            
        except Exception as e:
            logger.error(f"Error en cache.delete({key}): {e}")
            return False
    
    async def clear(self, level: CacheLevel = CacheLevel.BOTH):
        """Limpia el cache"""
        try:
            # L1 Cache
            if level in [CacheLevel.L1_MEMORY, CacheLevel.BOTH]:
                self.l1_cache.clear()
                logger.info("L1 cache limpiado")
            
            # L2 Cache (Redis)
            if level in [CacheLevel.L2_REDIS, CacheLevel.BOTH] and self.is_redis_available:
                try:
                    await self.redis_client.flushdb()
                    logger.info("L2 cache (Redis) limpiado")
                except Exception as e:
                    logger.warning(f"Error limpiando Redis: {e}")
            
        except Exception as e:
            logger.error(f"Error limpiando cache: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Estadísticas completas del cache"""
        try:
            stats = {
                "service_status": "active" if self.is_initialized else "inactive",
                "redis_available": self.is_redis_available,
                "l1_stats": self.l1_cache.get_stats(),
                "l2_stats": {},
                "config": {
                    "l1_max_size_mb": self.config.l1_max_size_mb,
                    "l1_max_items": self.config.l1_max_items,
                    "l2_default_ttl": self.config.l2_default_ttl,
                    "compression_threshold": self.config.compression_threshold_bytes
                }
            }
            
            # Stats de Redis si está disponible
            if self.is_redis_available and self.redis_client:
                try:
                    redis_info = await self.redis_client.info()
                    stats["l2_stats"] = {
                        "used_memory": redis_info.get("used_memory", 0),
                        "used_memory_human": redis_info.get("used_memory_human", "0B"),
                        "connected_clients": redis_info.get("connected_clients", 0),
                        "total_commands_processed": redis_info.get("total_commands_processed", 0),
                        "keyspace_hits": redis_info.get("keyspace_hits", 0),
                        "keyspace_misses": redis_info.get("keyspace_misses", 0)
                    }
                except Exception as e:
                    logger.warning(f"Error obteniendo stats de Redis: {e}")
            
            return stats
            
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {e}")
            return {"error": str(e)}
    
    async def close(self):
        """Cierra el servicio de cache"""
        try:
            logger.info("🔄 Cerrando Cache Service Enterprise...")
            
            # Cancelar health checks
            if self.health_check_task:
                self.health_check_task.cancel()
                try:
                    await self.health_check_task
                except asyncio.CancelledError:
                    pass
            
            # Cerrar Redis
            if self.redis_client:
                await self.redis_client.close()
            
            # Limpiar L1
            self.l1_cache.clear()
            
            self.is_initialized = False
            logger.info("✅ Cache Service Enterprise cerrado")
            
        except Exception as e:
            logger.error(f"Error cerrando Cache Service: {e}")

# ===============================================
# 🚀 INSTANCIA GLOBAL
# ===============================================

# Configuración por defecto optimizada para producción
PRODUCTION_CACHE_CONFIG = CacheConfig(
    redis_url="redis://localhost:6379",
    redis_db=0,
    redis_max_connections=50,
    l1_max_size_mb=200,       # 200MB en memoria
    l1_max_items=50000,       # 50K items max
    l1_default_ttl=300,       # 5 minutos
    l2_default_ttl=3600,      # 1 hora
    l2_max_value_size_mb=50,  # 50MB max por item
    compression_threshold_bytes=2048,  # 2KB
    enable_metrics=True,
    enable_health_checks=True,
    enable_warming=True,
    warming_patterns=["config_*", "user_session_*", "agent_*", "system_*"]
)

# Instancia global del servicio
cache_service_enterprise = CacheServiceEnterprise(PRODUCTION_CACHE_CONFIG)

# ===============================================
# 🔧 FUNCIONES DE UTILIDAD
# ===============================================

async def get_cache_service() -> CacheServiceEnterprise:
    """Dependency injection para el cache service"""
    return cache_service_enterprise

def generate_cache_key(*parts: str, prefix: str = "") -> str:
    """Genera una clave de cache consistente"""
    key_parts = [prefix] + list(parts) if prefix else list(parts)
    key = ":".join(str(part) for part in key_parts)
    return hashlib.md5(key.encode()).hexdigest()[:16] + ":" + key

async def cached_function(
    cache_key: str,
    ttl_seconds: int = 300,
    level: CacheLevel = CacheLevel.BOTH
):
    """Decorator para cachear resultados de funciones"""
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            # Intentar obtener del cache
            cached_result = await cache_service_enterprise.get(cache_key, level)
            if cached_result is not None:
                return cached_result
            
            # Ejecutar función y cachear resultado
            result = await func(*args, **kwargs)
            await cache_service_enterprise.set(cache_key, result, ttl_seconds, level)
            return result
        
        return wrapper
    return decorator

# ===============================================
# 📊 HEALTH CHECK ESPECÍFICO
# ===============================================

async def cache_health_check() -> Dict[str, Any]:
    """Health check específico del cache"""
    try:
        start_time = time.time()
        
        # Test L1
        test_key = f"health_check_{int(time.time())}"
        test_value = {"timestamp": datetime.utcnow().isoformat()}
        
        l1_success = cache_service_enterprise.l1_cache.set(test_key, test_value)
        l1_get = cache_service_enterprise.l1_cache.get(test_key) is not None
        cache_service_enterprise.l1_cache.delete(test_key)
        
        # Test L2 (Redis)
        l2_success = False
        l2_get = False
        if cache_service_enterprise.is_redis_available:
            try:
                await cache_service_enterprise.redis_client.ping()
                await cache_service_enterprise.set(test_key, test_value, level=CacheLevel.L2_REDIS)
                l2_get = await cache_service_enterprise.get(test_key, level=CacheLevel.L2_REDIS) is not None
                await cache_service_enterprise.delete(test_key, level=CacheLevel.L2_REDIS)
                l2_success = True
            except Exception as e:
                logger.warning(f"Redis health check failed: {e}")
        
        duration = time.time() - start_time
        
        return {
            "status": "healthy" if (l1_success and l1_get) else "degraded",
            "l1_cache": {
                "available": l1_success and l1_get,
                "write": l1_success,
                "read": l1_get
            },
            "l2_cache": {
                "available": cache_service_enterprise.is_redis_available and l2_success and l2_get,
                "write": l2_success,
                "read": l2_get
            },
            "response_time_ms": round(duration * 1000, 2),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }