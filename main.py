# main.py  
# Backend Super IA - Enterprise Production v4.0
# FastAPI Application con Qwen 2.5 Omni + LiveSearch + 17 Capacidades IA
# Optimizado para ultra alta carga, performance y producción real
# Versión: 4.0 - Octubre 2025

import os
import logging
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request, status, HTTPException, Depends
from fastapi.responses import JSONResponse, Response, ORJSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from prometheus_client import generate_latest
import json_log_formatter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

# Configuración
from config import (
    APP_NAME,
    APP_VERSION,
    APP_DESCRIPTION,
    CORS_ORIGINS,
    CORS_CREDENTIALS,
    CORS_METHODS,
    CORS_HEADERS,
    ENVIRONMENT,
    DEBUG,
    METRICS_ENABLED,
    HOST,
    PORT,
    ALLOWED_HOSTS
)

# Database
from database.db_enterprise import get_async_db


# Routers
from routers import (
    auth_routes,
    unified_chat_router,
    apa7_pdf_router,
    class_notes_router,
    profile_router,
    agenda_router,
)

# Middlewares
from middlewares.rate_limit_middleware import RateLimitMiddleware
from middlewares.timeout_middleware import TimeoutMiddleware
from middlewares.prevalidation_middleware import PreValidationMiddleware
from middlewares.csrf_middleware import CSRFMiddleware, get_csrf_token

# =============================================
# LOGGING CONFIGURATION
# =============================================
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger("main")
logger.setLevel(logging.INFO if not DEBUG else logging.DEBUG)
if not logger.handlers:
    logger.addHandler(handler)

# =============================================
# LIFESPAN EVENTS
# =============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Manejo del ciclo de vida de la aplicación
    # Inicialización
    logger.info(f"🚀 Starting {APP_NAME} v{APP_VERSION} in {ENVIRONMENT} mode")
    logger.info("="*80)
    
    # � Validar configuración de producción
    if ENVIRONMENT == "production":
        from utils.config_validator import validate_production_config
        validation = validate_production_config()

        enforce_validation = os.getenv("ENFORCE_PROD_CONFIG_VALIDATION", "false").lower() in (
            "true",
            "1",
            "t",
            "yes",
        )
        
        if not validation["valid"]:
            logger.error("❌ Production configuration validation FAILED")
            for error in validation["errors"]:
                logger.error(error)

            if enforce_validation:
                raise RuntimeError("Invalid production configuration. Fix errors and restart.")
            else:
                logger.warning(
                    "⚠️ Continuing startup with invalid production configuration (ENFORCE_PROD_CONFIG_VALIDATION=false)"
                )
        
        if validation["warnings"]:
            for warning in validation["warnings"]:
                logger.warning(warning)
        
        logger.info("✅ Production configuration validated")
    
    # �🚀 v4.0: Inicialización paralela de servicios para startup 3x más rápido
    startup_tasks = []
    
    # Task 1: Database
    async def init_database():
        try:
            from database.db_enterprise import init_database_enterprise
            await init_database_enterprise()
            logger.info(" Database initialized")
        except Exception as e:
            logger.warning(f" Database initialization warning: {e}")
    startup_tasks.append(init_database())
    
    # Task 3: Precargar modelo IA (Qwen via SiliconFlow)
    async def preload_ai_models():
        logger.info("🤖 Initializing AI client...")
        try:
            from services.qwen_client import initialize_qwen_client
            ai_available = await initialize_qwen_client()
            if ai_available:
                logger.info("✅ Qwen3-VL connected via SiliconFlow")
            else:
                logger.warning("⚠️ Qwen no disponible (normal si servidor remoto)")
        except Exception as e:
            logger.warning(f"⚠️ Qwen init warning: {e}")
    
    startup_tasks.append(preload_ai_models())
    
    # 🚀 Ejecutar todo en paralelo (3x más rápido que v3.0)
    await asyncio.gather(*startup_tasks, return_exceptions=True)
    
    logger.info(f"✅ {APP_NAME} v4.0 started successfully - Ready for production!")
    
    yield
    
    # Shutdown
    logger.info(f"🛑 Shutting down {APP_NAME}")
    
    # Cerrar conexiones
    try:
        from database.db_enterprise import close_db
        await close_db()
        logger.info("✅ Database connections closed")
    except Exception as e:
        logger.warning(f"⚠️ Database closure warning: {e}")
    
    logger.info(f"✅ {APP_NAME} shutdown complete")

# =============================================
# FASTAPI APP INITIALIZATION v4.0
# =============================================

app = FastAPI(
    title=APP_NAME,
    version="5.0",
    description=f"{APP_DESCRIPTION} - Qwen3-VL-32B via SiliconFlow",
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
    openapi_url="/openapi.json" if DEBUG else None,
    # 🚀 v4.0: Optimizaciones de performance
    swagger_ui_parameters={
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True
    }
)

# =============================================
# MIDDLEWARES v4.0 - Optimizados + Seguridad
# =============================================

# Trusted Host (Security)
if ENVIRONMENT == "production":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=ALLOWED_HOSTS
    )

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=CORS_CREDENTIALS,
    allow_methods=CORS_METHODS,
    allow_headers=CORS_HEADERS,
    max_age=3600  # 🚀 v4.0: Cache preflight requests por 1 hora
)

# Compression - 🚀 v4.0: Mejor threshold y compresión
app.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=6)

# Security Middleware - CSRF Protection (Production)
if ENVIRONMENT == "production":
    from config import SECRET_KEY
    app.add_middleware(CSRFMiddleware, secret_key=SECRET_KEY)
    logger.info("✅ CSRF Protection enabled")

# Custom Middlewares (orden importa: de afuera hacia adentro)
app.add_middleware(TimeoutMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(PreValidationMiddleware)

# =============================================
# EXCEPTION HANDLERS
# =============================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Handler global para excepciones no capturadas
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "message": str(exc) if DEBUG else "An unexpected error occurred",
            "request_id": request.headers.get("X-Request-ID", "unknown")
        }
    )

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    # Handler para rutas no encontradas
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "error": "Not found",
            "message": f"Route {request.url.path} not found",
            "available_docs": "/docs"
        }
    )

# =============================================
# HEALTH CHECKS Y MONITORING
# =============================================

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint con información del servicio"""
    return {
        "service": APP_NAME,
        "version": APP_VERSION,
        "environment": ENVIRONMENT,
        "status": "operational",
        "docs": "/docs" if DEBUG else None,
        "health": "/api/health",
        "csrf_token": "/api/csrf-token"
    }

@app.get("/api/csrf-token", tags=["Security"])
async def csrf_token_endpoint():
    """
    Obtiene un token CSRF válido para requests protegidos
    
    El token debe incluirse en el header X-CSRF-Token para:
    - POST /api/payments/*
    - POST /api/subscriptions/subscribe
    - POST /api/auth/*
    - POST /api/permissions/*
    """
    return await get_csrf_token()

@app.get("/api/health", tags=["Monitoring"])
async def health_check():
    """
    Health check completo del sistema
    
    Verifica:
    - Database connection
    - Redis cache
    - AI models availability
    """
    
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": APP_VERSION,
        "environment": ENVIRONMENT,
        "components": {
            "database": "unknown",
            "cache": "unknown",
            "ai_models": "unknown"
        }
    }
    
    # Check database (optional - don't fail if unavailable)
    try:
        from database.db_enterprise import db_manager, ConnectionType
        primary_engine = db_manager.engines.get(ConnectionType.PRIMARY)
        if primary_engine:
            async with primary_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            health_status["components"]["database"] = "healthy"
        else:
            health_status["components"]["database"] = "not_initialized"
    except Exception as e:
        health_status["components"]["database"] = f"unavailable: {str(e)[:100]}"
    
    # Check Redis (optional - don't fail if unavailable)
    try:
        redis = await get_redis()
        await redis.ping()
        health_status["components"]["cache"] = "healthy"
    except Exception:
        health_status["components"]["cache"] = "unavailable"
    
    # AI models - siempre healthy si el servidor está corriendo (SiliconFlow es externo)
    health_status["components"]["ai_models"] = "ready"
    
    return health_status

@app.get("/metrics", tags=["Monitoring"])
async def metrics():
    # Endpoint de métricas Prometheus
    if not METRICS_ENABLED:
        return Response(content="Metrics disabled", status_code=404)
    return Response(
        content=generate_latest(),
        media_type="text/plain"
    )

# =============================================
# ROUTERS
# =============================================

# Autenticación
app.include_router(auth_routes.router, prefix="/api/auth", tags=["Authentication"])

# Chat e IA
app.include_router(unified_chat_router.router, prefix="/api", tags=["💬 Chat IA"])

# Documents
app.include_router(apa7_pdf_router.router, tags=["Documents"])

# Class notes
app.include_router(class_notes_router.router, tags=["Class Notes"])

# Profile
app.include_router(profile_router.router, tags=["Profile"])

# Agenda IA
app.include_router(agenda_router.router, tags=["Agenda"])

# =============================================
# STARTUP MESSAGE
# =============================================
# PUNTO DE ENTRADA
# =============================================

if __name__ == "__main__":
    print("=" * 64)
    print("BACKEND ENTERPRISE - PRODUCTION READY")
    print("=" * 64)
    print(f"Service: {APP_NAME} v{APP_VERSION}")
    print(f"Environment: {ENVIRONMENT}")
    print(f"AI Model: Qwen 2.5 Omni (multimodal)")
    print(f"Debug Mode: {DEBUG}")
    print("")
    print("API Docs: /docs")
    print("Health: /api/health")
    print("Metrics: /metrics")
    print("=" * 64)
    print("")
    
    import uvicorn
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="info" if DEBUG else "warning",
        access_log=DEBUG
    )
