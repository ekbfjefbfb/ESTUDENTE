"""
Database Enterprise v5.0 - Production Optimized
Sistema de base de datos enterprise con máxima performance:
- Connection pooling optimizado (20 connections + 10 overflow)
- Circuit breakers + heartbeat keep-alive
- Métricas y monitoring avanzado
- Compatible con PostgreSQL + SQLite (desarrollo)
"""
import asyncio
import os
import time
import logging
import enum
import socket
from typing import Dict, Any, Optional, AsyncGenerator, List
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from dataclasses import dataclass
from collections import defaultdict

from config import ENVIRONMENT, DATABASE_URL as CONFIG_DATABASE_URL

# SQLAlchemy Enterprise
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text, event, pool
from sqlalchemy.exc import DisconnectionError, OperationalError, IntegrityError
from sqlalchemy.engine import events

# Utils y Métricas
from utils.safe_metrics import Counter, Histogram, Gauge

logger = logging.getLogger("db_enterprise")

# ===============================================
# 📊 CONFIGURACIÓN Y ENUMS
# ===============================================

class ConnectionType(enum.Enum):
    PRIMARY = "primary"
    READONLY = "readonly" 
    ANALYTICS = "analytics"

@dataclass
class DatabaseConfig:
    """Configuración enterprise v4.0 - Ultra optimizada"""
    primary_url: str
    readonly_url: Optional[str] = None
    analytics_url: Optional[str] = None
    primary_pool_size: int = 20  # Aumentado para soportar carga multiusuario real
    primary_max_overflow: int = 10  # Permitir overflow controlado para picos de carga
    readonly_pool_size: int = 5
    readonly_max_overflow: int = 5
    pool_timeout: int = 30
    pool_recycle: int = 1800  # 30 min — estándar PostgreSQL (120s era demasiado agresivo)
    query_timeout: int = 30
    enable_query_cache: bool = True
    enable_metrics: bool = True
    enable_circuit_breaker: bool = True
    pool_pre_ping: bool = True  # CRÍTICO: SQLAlchemy verifica la salud antes de entregar del pool

# ===============================================
# 📈 MÉTRICAS ENTERPRISE
# ===============================================

class DatabaseMetrics:
    """Métricas avanzadas para base de datos"""
    
    def __init__(self):
        self.query_counter = Counter(
            'db_queries_total',
            'Total database queries',
            ['connection_type', 'operation', 'status']
        )
        
        self.query_duration = Histogram(
            'db_query_duration_seconds',
            'Database query duration',
            ['connection_type', 'operation']
        )
        
        self.error_counter = Counter(
            'db_errors_total',
            'Database errors',
            ['error_type', 'connection_type']
        )
        
        self.active_connections = Gauge(
            'db_active_connections',
            'Active database connections',
            ['connection_type']
        )

# ===============================================
# 🎯 CIRCUIT BREAKER SIMPLE
# ===============================================

class SimpleCircuitBreaker:
    """Circuit breaker simplificado para base de datos"""
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    async def call(self, func, *args, **kwargs):
        """Ejecuta función con circuit breaker"""
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "HALF_OPEN"
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
            
            raise e

# ===============================================
# 🏗️ DATABASE ENTERPRISE MANAGER
# ===============================================

class DatabaseEnterpriseManager:
    """Manager avanzado de base de datos enterprise"""
    
    # Tamaño máximo del query cache en memoria
    _QUERY_CACHE_MAX_SIZE = 500

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.engines: Dict[ConnectionType, Any] = {}
        self.session_makers: Dict[ConnectionType, Any] = {}
        self.circuit_breakers: Dict[ConnectionType, SimpleCircuitBreaker] = {}
        self.metrics = DatabaseMetrics()
        self.query_cache: Dict[str, Any] = {}  # Bounded: se limpia si supera _QUERY_CACHE_MAX_SIZE
        self.initialized = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._is_postgresql: bool = False  # Se detecta en initialize()
    
    async def _heartbeat_loop(self):
        """Loop de heartbeat para evitar que la DB se duerma (Keep-Alive)"""
        interval = int(os.getenv("DB_HEARTBEAT_INTERVAL", "300")) # 5 min por defecto
        logger.info(f"💓 Iniciando Heartbeat Loop (intervalo: {interval}s)")
        
        while True:
            try:
                if self.initialized:
                    # Usar el engine directamente para un ping rápido
                    engine = self.engines.get(ConnectionType.PRIMARY)
                    if engine:
                        async with engine.begin() as conn:
                            await conn.execute(text("SELECT 1"))
                        logger.debug("💓 Heartbeat DB: Ping exitoso")
            except (OperationalError, DisconnectionError) as e:
                logger.warning(f"⚠️ Heartbeat DB: Error de conexión (intentando reconectar): {e}")
                # Forzar reinicialización si es un error de conexión persistente
                self.initialized = False
                try:
                    await self.initialize()
                except Exception as init_e:
                    logger.error(f"❌ Falló reconexión en Heartbeat: {init_e}")
            except Exception as e:
                logger.warning(f"⚠️ Heartbeat DB: Error inesperado: {e}")
            
            await asyncio.sleep(interval)

    async def initialize(self):
        """Inicializa todas las conexiones de base de datos con reintentos"""
        if self.initialized:
            return

        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                logger.info(f"🚀 Inicializando Database Enterprise Manager (intento {attempt + 1}/{max_retries})")
                
                # Validar DNS antes de intentar conectar
                if not self._validate_dns(self.config.primary_url):
                    if attempt < max_retries - 1:
                        logger.warning(f"⚠️ DNS no resoluble para la DB principal, reintentando en {retry_delay}s...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        raise OperationalError(None, None, f"Could not translate host name for {self.config.primary_url}")

                # Configurar engine principal
                await self._setup_engine(ConnectionType.PRIMARY, self.config.primary_url)
                
                # Configurar engine readonly si está disponible
                if self.config.readonly_url:
                    await self._setup_engine(ConnectionType.READONLY, self.config.readonly_url)
                
                # Configurar engine analytics si está disponible
                if self.config.analytics_url:
                    await self._setup_engine(ConnectionType.ANALYTICS, self.config.analytics_url)
                
                self.initialized = True
                # Detectar tipo de DB para comandos específicos
                self._is_postgresql = "postgresql" in self.config.primary_url.lower()
                logger.info(f"✅ Database Enterprise Manager inicializado (postgresql={self._is_postgresql})")

                # Iniciar Heartbeat en background
                if self._heartbeat_task is None or self._heartbeat_task.done():
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                break
                
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"⚠️ Error inicializando Database Manager, reintentando: {e}")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f"❌ Error fatal inicializando Database Manager tras {max_retries} intentos: {e}")
                    raise

    def _validate_dns(self, url: str) -> bool:
        """Verifica si el host de la URL es resoluble"""
        try:
            parsed = urlparse(url)
            host = parsed.hostname
            if not host:
                return True # Probablemente sqlite o URL malformada que fallará después
            
            socket.gethostbyname(host)
            return True
        except socket.gaierror:
            logger.error(f"❌ Error de DNS: No se pudo resolver el host '{host}'")
            return False
        except Exception as e:
            logger.error(f"⚠️ Error validando DNS: {e}")
            return True # Continuar y dejar que SQLAlchemy maneje otros errores
    
    async def _setup_engine(self, connection_type: ConnectionType, database_url: str):
        """Configura engine para tipo de conexión específico"""
        
        # Configuración según tipo de conexión
        pool_size = self.config.primary_pool_size
        max_overflow = self.config.primary_max_overflow
        
        if connection_type == ConnectionType.READONLY:
            pool_size = self.config.readonly_pool_size
            max_overflow = self.config.readonly_max_overflow
        
        # Crear engine
        engine = create_async_engine(
            database_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=self.config.pool_timeout,
            pool_recycle=self.config.pool_recycle,
            pool_pre_ping=self.config.pool_pre_ping,
            echo=False,
            future=True
        )
        
        # Crear session maker
        session_maker = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        # Configurar circuit breaker
        circuit_breaker = SimpleCircuitBreaker()
        
        # Almacenar configuraciones
        self.engines[connection_type] = engine
        self.session_makers[connection_type] = session_maker
        self.circuit_breakers[connection_type] = circuit_breaker
        
        logger.info(f"✅ Engine {connection_type.value} configurado")
    
    @asynccontextmanager
    async def get_session(
        self,
        connection_type: ConnectionType = ConnectionType.PRIMARY,
        enable_circuit_breaker: bool = True
    ) -> AsyncGenerator[AsyncSession, None]:
        """Obtiene sesión de base de datos con circuit breaker y reintentos"""
        
        if not self.initialized:
            await self.initialize()
        
        if connection_type not in self.engines:
            connection_type = ConnectionType.PRIMARY
        
        session_maker = self.session_makers[connection_type]
        circuit_breaker = self.circuit_breakers[connection_type]
        
        start_time = time.time()
        max_retries = 2
        
        for attempt in range(max_retries + 1):
            session = None
            try:
                if enable_circuit_breaker and self.config.enable_circuit_breaker:
                    session = await circuit_breaker.call(session_maker)
                else:
                    session = session_maker()
                
                async with session:
                    # Configurar timeout por sesión (solo PostgreSQL)
                    if self._is_postgresql:
                        try:
                            await session.execute(
                                text(f"SET statement_timeout = '{self.config.query_timeout * 1000}'")
                            )
                        except Exception:
                            pass  # Non-critical: no bloquear si falla
                    
                    self.metrics.query_counter.inc(
                        labels=[connection_type.value, 'session_start', 'success']
                    )
                    
                    yield session
                    return # Éxito, salir del loop de reintentos
                    
            except (OperationalError, DisconnectionError) as e:
                if attempt < max_retries:
                    wait_time = 0.5 * (attempt + 1)
                    logger.warning(f"⚠️ Error de conexión en sesión {connection_type.value} (intento {attempt+1}): {e}. Reintentando en {wait_time}s...")
                    if session:
                        await session.close()
                    await asyncio.sleep(wait_time)
                    continue
                
                self.metrics.error_counter.inc(
                    labels=['connection_error', connection_type.value]
                )
                logger.error(f"ConnectionError final en {connection_type.value} tras {max_retries} reintentos: {e}")
                raise
                
            except IntegrityError as e:
                if session:
                    await session.rollback()
                self.metrics.error_counter.inc(
                    labels=['integrity_error', connection_type.value]
                )
                logger.error(f"IntegrityError en {connection_type.value}: {e}")
                raise
                
            except Exception as e:
                if session:
                    await session.rollback()
                
                self.metrics.error_counter.inc(
                    labels=['unknown_error', connection_type.value]
                )
                logger.error(f"Error inesperado en sesión {connection_type.value}: {e}")
                raise
                
            finally:
                duration = time.time() - start_time
                self.metrics.query_duration.observe(duration)
    
    async def execute_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        connection_type: ConnectionType = ConnectionType.PRIMARY,
        cache_key: Optional[str] = None
    ) -> Any:
        """Ejecuta query con optimizaciones enterprise"""
        
        start_time = time.time()
        
        # Check cache si está habilitado
        if cache_key and self.config.enable_query_cache:
            if cache_key in self.query_cache:
                self.metrics.query_counter.inc(
                    labels=[connection_type.value, 'query', 'cache_hit']
                )
                return self.query_cache[cache_key]
        
        try:
            async with self.get_session(connection_type) as session:
                if params:
                    result = await session.execute(text(query), params)
                else:
                    result = await session.execute(text(query))
                
                # Procesar resultado
                if result.returns_rows:
                    data = result.fetchall()
                else:
                    data = result.rowcount
                
                # Guardar en cache si está configurado
                if cache_key and self.config.enable_query_cache:
                    # Evitar crecimiento infinito del cache
                    if len(self.query_cache) >= self._QUERY_CACHE_MAX_SIZE:
                        # Eliminar la mitad más antigua (FIFO)
                        keys_to_remove = list(self.query_cache.keys())[:self._QUERY_CACHE_MAX_SIZE // 2]
                        for k in keys_to_remove:
                            self.query_cache.pop(k, None)
                    self.query_cache[cache_key] = data
                
                self.metrics.query_counter.inc(
                    labels=[connection_type.value, 'query', 'success']
                )
                
                return data
                
        except Exception as e:
            self.metrics.query_counter.inc(
                labels=[connection_type.value, 'query', 'error']
            )
            logger.error(f"Error ejecutando query: {e}")
            raise
        
        finally:
            duration = time.time() - start_time
            self.metrics.query_duration.observe(duration)
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Obtiene estado de salud de todas las conexiones"""
        health_status = {
            "overall_status": "healthy",
            "connections": {},
            "metrics": {
                "total_engines": len(self.engines),
                "query_cache_size": len(self.query_cache)
            },
            "timestamp": time.time()
        }
        
        for conn_type, engine in self.engines.items():
            try:
                start_time = time.time()
                async with engine.begin() as conn:
                    await conn.execute(text("SELECT 1"))
                
                response_time = (time.time() - start_time) * 1000
                
                health_status["connections"][conn_type.value] = {
                    "status": "healthy",
                    "response_time_ms": round(response_time, 2),
                    "circuit_breaker_state": self.circuit_breakers[conn_type].state
                }
                
            except Exception as e:
                health_status["connections"][conn_type.value] = {
                    "status": "unhealthy",
                    "error": str(e),
                    "circuit_breaker_state": self.circuit_breakers[conn_type].state
                }
                health_status["overall_status"] = "degraded"
        
        return health_status
    
    async def close(self):
        """Cierra todas las conexiones"""
        try:
            logger.info("🔄 Cerrando Database Enterprise Manager")
            
            for conn_type, engine in self.engines.items():
                await engine.dispose()
                logger.info(f"✅ Engine {conn_type.value} cerrado")
            
            logger.info("✅ Database Enterprise Manager cerrado")
            
        except Exception as e:
            logger.error(f"❌ Error cerrando Database Manager: {e}")

# ===============================================
# 🚀 CONFIGURACIÓN GLOBAL
# ===============================================

def create_database_config() -> DatabaseConfig:
    """Crea configuración de base de datos desde environment"""
    
    # URL principal
    primary_url = os.getenv("DATABASE_URL") or CONFIG_DATABASE_URL
    if not primary_url:
        raise RuntimeError(
            "❌ DATABASE_URL no está definido. "
            "Configura la URL de Nhost PostgreSQL."
        )
    
    # Convertir a asyncpg si es necesario
    if primary_url.startswith("postgresql://"):
        primary_url = primary_url.replace("postgresql://", "postgresql+asyncpg://")
    
    # URLs adicionales (opcional)
    readonly_url = os.getenv("DATABASE_READONLY_URL")
    if readonly_url and readonly_url.startswith("postgresql://"):
        readonly_url = readonly_url.replace("postgresql://", "postgresql+asyncpg://")
    
    analytics_url = os.getenv("DATABASE_ANALYTICS_URL")
    if analytics_url and analytics_url.startswith("postgresql://"):
        analytics_url = analytics_url.replace("postgresql://", "postgresql+asyncpg://")
    
    return DatabaseConfig(
        primary_url=primary_url,
        readonly_url=readonly_url,
        analytics_url=analytics_url,
        primary_pool_size=int(os.getenv("DB_PRIMARY_POOL_SIZE", "20")),
        primary_max_overflow=int(os.getenv("DB_PRIMARY_MAX_OVERFLOW", "10")),
        readonly_pool_size=int(os.getenv("DB_READONLY_POOL_SIZE", "5")),
        readonly_max_overflow=int(os.getenv("DB_READONLY_MAX_OVERFLOW", "5")),
        pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
        pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),
        query_timeout=int(os.getenv("DB_QUERY_TIMEOUT", "30")),
        enable_query_cache=os.getenv("DB_ENABLE_QUERY_CACHE", "true").lower() == "true",
        enable_metrics=os.getenv("DB_ENABLE_METRICS", "true").lower() == "true",
        enable_circuit_breaker=os.getenv("DB_ENABLE_CIRCUIT_BREAKER", "true").lower() == "true"
    )

# Instancia global
db_config = create_database_config()
db_manager = DatabaseEnterpriseManager(db_config)

# ===============================================
# 🔧 FUNCIONES DE UTILIDAD - SIMPLE Y DIRECTO
# ===============================================

async def get_primary_session():
    """Obtiene sesión de escritura principal - simple y directo"""
    if not db_manager.initialized:
        await db_manager.initialize()
    
    session_maker = db_manager.session_makers.get(ConnectionType.PRIMARY)
    return session_maker()


async def get_readonly_session():
    """Obtiene sesión de solo lectura"""
    if not db_manager.initialized:
        await db_manager.initialize()
    
    connection_type = (
        ConnectionType.READONLY 
        if ConnectionType.READONLY in db_manager.engines 
        else ConnectionType.PRIMARY
    )
    session_maker = db_manager.session_makers.get(connection_type)
    session = session_maker()
    return session


async def get_analytics_session():
    """Obtiene sesión para analytics"""
    if not db_manager.initialized:
        await db_manager.initialize()
    
    connection_type = (
        ConnectionType.ANALYTICS 
        if ConnectionType.ANALYTICS in db_manager.engines 
        else ConnectionType.READONLY
        if ConnectionType.READONLY in db_manager.engines
        else ConnectionType.PRIMARY
    )
    session_maker = db_manager.session_makers.get(connection_type)
    session = session_maker()
    return session


# Compatibilidad con API anterior - mantener nombres originales
async def get_async_db():
    """Async generator compatible con FastAPI Depends().
    
    Uso:
        db: AsyncSession = Depends(get_async_db)
    """
    session = await get_primary_session()
    try:
        yield session
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        raise
    finally:
        await session.close()


async def get_db_session():
    """Retorna sesión directa (NO para Depends, sí para uso interno)."""
    return await get_primary_session()

# ===============================================
# 🏗️ FUNCIONES DE INICIALIZACIÓN
# ===============================================

async def init_database_enterprise():
    """Inicializa sistema de base de datos enterprise"""
    try:
        logger.info("🚀 Inicializando Database Enterprise System")
        
        # Inicializar manager
        await db_manager.initialize()
        
        # Crear tablas en modo test
        if os.getenv("ENV") == "test":
            try:
                from models.models import Base as ModelsBase
                primary_engine = db_manager.engines[ConnectionType.PRIMARY]
                async with primary_engine.begin() as conn:
                    await conn.run_sync(ModelsBase.metadata.create_all)
                logger.info("✅ Tablas de test creadas")
            except Exception as e:
                logger.warning(f"⚠️ Error creando tablas de test: {e}")
        
        logger.info("✅ Database Enterprise System inicializado")
        
    except Exception as e:
        logger.error(f"❌ Error inicializando Database Enterprise: {e}")
        raise

async def close_database_enterprise():
    """Cierra sistema de base de datos enterprise"""
    await db_manager.close()

# Compatibilidad
init_database = init_database_enterprise
close_database = close_database_enterprise

# ===============================================
# 📊 EXPORTS
# ===============================================

__all__ = [
    "db_manager",
    "DatabaseEnterpriseManager",
    "DatabaseConfig",
    "ConnectionType",
    "get_primary_session",
    "get_readonly_session",
    "get_analytics_session",
    "get_async_db",
    "get_db_session",
    "init_database_enterprise",
    "close_database_enterprise",
    "init_database",
    "close_database"
]

logger.info("🗄️ Database Enterprise Module cargado exitosamente")
