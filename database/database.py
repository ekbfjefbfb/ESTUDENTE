"""
Database Simple para sistema de Clientes Multi-Sector
Versión simplificada de db_enterprise.py para compatibilidad
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL, DATABASE_URL_SYNC

# Base para modelos SQLAlchemy
Base = declarative_base()

# ===============================================
# ASYNC DATABASE (FastAPI endpoints)
# ===============================================

# Convertir sqlite:/// a sqlite+aiosqlite:/// para async
ASYNC_DATABASE_URL = DATABASE_URL or "sqlite:///./backend_super.db"
if ASYNC_DATABASE_URL.startswith("sqlite:///"):
    ASYNC_DATABASE_URL = ASYNC_DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///")

# Engine async
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if "sqlite" in ASYNC_DATABASE_URL else {}
)

# Session maker async
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_async_db():
    """
    Dependency para FastAPI endpoints
    Usage:
        @app.get("/clients")
        async def get_clients(db: AsyncSession = Depends(get_async_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# ===============================================
# SYNC DATABASE (Celery tasks, scripts)
# ===============================================

# Engine sync
SYNC_DATABASE_URL = DATABASE_URL_SYNC or "sqlite:///./backend_super.db"
sync_engine = create_engine(
    SYNC_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if "sqlite" in SYNC_DATABASE_URL else {}
)

# Session maker sync
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=sync_engine
)

def get_db_sync():
    """
    Para tareas Celery y scripts síncronos
    Usage:
        with get_db_sync() as db:
            clients = db.query(Client).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ===============================================
# INIT DB
# ===============================================

async def init_db():
    """Inicializar tablas en la base de datos"""
    async with async_engine.begin() as conn:
        # Importar todos los modelos aquí para que se registren
        from models.client import Client, ReportLog, Task, Asset
        
        # Crear todas las tablas
        await conn.run_sync(Base.metadata.create_all)


# ===============================================
# CLOSE DB
# ===============================================

async def close_db():
    """Cerrar conexiones de base de datos"""
    await async_engine.dispose()
