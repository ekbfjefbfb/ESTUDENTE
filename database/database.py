"""
Database Unified - Pareto Optimized v6.0
Consolidación de acceso a datos para máxima performance y mantenibilidad.
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker

# Re-exportar desde el sistema enterprise optimizado
from database.db_enterprise import (
    db_manager, 
    get_async_db as get_async_db_enterprise,
    get_primary_session,
    init_database_enterprise,
    close_database_enterprise,
    ConnectionType
)
from config import DATABASE_URL_SYNC

# Base para modelos SQLAlchemy (Compartida)
Base = declarative_base()

# ===============================================
# ASYNC DATABASE (Compatibilidad)
# ===============================================

async def get_async_db():
    """Proxy para el sistema enterprise asíncrono"""
    async for session in get_async_db_enterprise():
        yield session

# ===============================================
# SYNC DATABASE (Scripts y Tareas)
# ===============================================

# Engine sync optimizado
sync_engine = create_engine(
    DATABASE_URL_SYNC,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=5
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=sync_engine
)

def get_db_sync():
    """Provee sesión síncrona con manejo automático"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db():
    """Alias legacy esperado por routers FastAPI síncronos."""
    yield from get_db_sync()

# ===============================================
# CICLO DE VIDA (Unified)
# ===============================================

async def init_db():
    """Inicializa el sistema enterprise y crea tablas si es necesario"""
    await init_database_enterprise()
    
    # Solo crear tablas automáticamente en entornos no-prod o si se requiere
    from os import getenv
    if getenv("ENVIRONMENT") != "production":
        primary_engine = db_manager.engines.get(ConnectionType.PRIMARY)
        if primary_engine:
            async with primary_engine.begin() as conn:
                from models.models import Base as ModelsBase
                await conn.run_sync(ModelsBase.metadata.create_all)

async def close_db():
    """Cierre centralizado"""
    await close_database_enterprise()
    if sync_engine:
        sync_engine.dispose()
