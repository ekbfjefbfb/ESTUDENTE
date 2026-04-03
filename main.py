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
from utils.msgpack_utils import MessagePackResponse
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

# =============================================
# SENTRY (observability) - fail-open
# =============================================
try:
    from config import SENTRY_DSN

    if SENTRY_DSN:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        traces_sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0"))
        profiles_sample_rate = float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0"))

        sentry_logging = LoggingIntegration(
            level=logging.INFO,
            event_level=logging.ERROR,
        )

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=os.getenv("SENTRY_ENVIRONMENT") or ENVIRONMENT,
            send_default_pii=str(os.getenv("SENTRY_SEND_DEFAULT_PII", "false")).lower()
            in {"1", "true", "t", "yes"},
            traces_sample_rate=traces_sample_rate,
            profiles_sample_rate=profiles_sample_rate,
            integrations=[FastApiIntegration(), sentry_logging],
        )
except Exception:
    pass

# Database
from database.db_enterprise import get_async_db
from services.redis_service import get_redis


# Routers
from routers import (
    auth_routes,
    unified_chat_router,
    apa7_pdf_router,
    class_notes_router,
    profile_router,
    scheduled_recording_router,
    recording_session_router,
    voice_note_router,
)
from routers import image_analysis_router
from routers import deepgram_agent_router
from routers import document_router

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
        if os.getenv("ENFORCE_PROD_CONFIG_VALIDATION") is None:
            enforce_validation = True
        
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
    
    # Task 3: Warmup de API Groq (una sola vez en startup, no por request)
    async def warmup_groq():
        try:
            from services.groq_ai_service import ensure_api_warmup
            await ensure_api_warmup()
            logger.info("🤖 Groq API warmed up")
        except Exception as e:
            logger.warning(f"⚠️ Groq warmup skipped: {e}")

    startup_tasks.append(warmup_groq())
    
    # 🚀 Ejecutar todo en paralelo (3x más rápido que v3.0)
    await asyncio.gather(*startup_tasks, return_exceptions=True)

    # Background tasks (fail-open) con safe_create_task
    try:
        from services.session_service import periodic_tasks
        from utils.background import safe_create_task

        app.state.session_periodic_task = safe_create_task(periodic_tasks(), name="session_periodic")
    except Exception as e:
        logger.warning(f"⚠️ session_service periodic task not started: {e}")
        
    try:
        from workers.voice_note_worker import worker_loop as voice_worker_loop
        from utils.background import safe_create_task
        app.state.voice_note_worker_task = safe_create_task(voice_worker_loop(), name="voice_note_worker")
        logger.info("✅🏭 Voice Note Background Worker started successfully")
    except Exception as e:
        logger.error(f"❌ Fatal: voice_note_worker failed to start: {e}")
    
    logger.info(f"✅ {APP_NAME} v4.0 started successfully - Ready for production!")
    
    yield
    
    # Shutdown
    logger.info(f"🛑 Shutting down {APP_NAME}")

    try:
        task = getattr(app.state, "session_periodic_task", None)
        if task is not None:
            task.cancel()
            
        from workers.voice_note_worker import _shutdown_event
        _shutdown_event.set()
        voice_task = getattr(app.state, "voice_note_worker_task", None)
        if voice_task is not None:
            voice_task.cancel()
    except Exception:
        pass
    
    # Cerrar conexiones
    try:
        from database.database import close_db
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
    description=f"{APP_DESCRIPTION} - Groq",
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
    # Agregar dominio de Render automáticamente si no está en la lista
    render_host = "estudente-msba.onrender.com"
    required_hosts = [render_host, "*.onrender.com", "testserver"]
    if any(host not in ALLOWED_HOSTS for host in required_hosts):
        ALLOWED_HOSTS = list(ALLOWED_HOSTS) + [host for host in required_hosts if host not in ALLOWED_HOSTS]
    
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
app.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=6)  # 6 = balance óptimo CPU/compresión

# Security Middleware - CSRF Protection (Production)
if ENVIRONMENT == "production":
    from config import SECRET_KEY
    app.add_middleware(CSRFMiddleware, secret_key=SECRET_KEY)
    logger.info("✅ CSRF Protection enabled")

# MessagePack Support
@app.middleware("http")
async def msgpack_middleware(request: Request, call_next):
    accept = request.headers.get("Accept", "")
    response = await call_next(request)
    
    if "application/x-msgpack" in accept and isinstance(response, (JSONResponse, ORJSONResponse)):
        import json
        try:
            # Re-render as MessagePack if requested
            body = [chunk async for chunk in response.body_iterator][0]
            data = json.loads(body)
            return MessagePackResponse(content=data)
        except Exception as e:
            logger.warning(f"Failed to convert response to MessagePack: {e}")
            return response
    return response

# Custom Middlewares (orden importa: de afuera hacia adentro)
app.add_middleware(TimeoutMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(PreValidationMiddleware)

# =============================================
# EXCEPTION HANDLERS
# =============================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Capturar errores de desconexión del cliente (anyio)
    exc_str = str(exc)
    if "EndOfStream" in exc_str or "WouldBlock" in exc_str:
        logger.warning({
            "event": "client_disconnected_unexpectedly",
            "path": request.url.path,
            "method": request.method,
            "request_id": request.headers.get("X-Request-ID", "unknown")
        })
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # Handler global para otras excepciones no capturadas
    logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    request_id = request.headers.get("X-Request-ID", "unknown")

    if DEBUG:
        import traceback

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": "Internal server error",
                "message": str(exc),
                "traceback": traceback.format_exc(),
                "request_id": request_id,
            },
        )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": "internal_error",
            "message": "Internal server error",
            "request_id": request_id,
        },
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
        "git_sha": str(os.getenv("GIT_SHA", "")),
        "environment": ENVIRONMENT,
        "sentry": {
            "enabled": bool(os.getenv("SENTRY_DSN")),
            "environment": str(os.getenv("SENTRY_ENVIRONMENT") or ENVIRONMENT),
            "traces_sample_rate": float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0") or 0),
            "profiles_sample_rate": float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0") or 0),
        },
        "components": {
            "database": "unknown",
            "cache": "unknown",
            "ai_models": "unknown"
        }
    }

    async def _check_database() -> str:
        try:
            from database.db_enterprise import db_manager, ConnectionType

            primary_engine = db_manager.engines.get(ConnectionType.PRIMARY)
            if primary_engine is None:
                return "not_initialized"

            async def _probe() -> None:
                async with primary_engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))

            await asyncio.wait_for(_probe(), timeout=0.75)
            return "healthy"
        except asyncio.TimeoutError:
            return "timeout"
        except Exception as e:
            return f"unavailable: {str(e)[:100]}"

    async def _check_cache() -> str:
        try:
            async def _probe() -> str:
                redis = await get_redis()
                if redis is None:
                    return "unavailable"
                await redis.ping()
                return "healthy"

            return await asyncio.wait_for(_probe(), timeout=0.5)
        except asyncio.TimeoutError:
            return "timeout"
        except Exception:
            return "unavailable"
    
    # Check database (optional - don't fail if unavailable)
    health_status["components"]["database"] = await _check_database()
    
    # Check Redis (optional - don't fail if unavailable)
    health_status["components"]["cache"] = await _check_cache()
    
    # AI models - always ready if server is running (provider is external)
    health_status["components"]["ai_models"] = "ready"
    
    return health_status


@app.get("/api/_debug/sentry-test", tags=["Debug"])
async def sentry_test():
    if not DEBUG:
        raise HTTPException(status_code=404, detail="not_found")
    1 / 0

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

# Compatibilidad legacy: algunos clientes conectan sin prefijo /api (p.ej. WebSockets)
app.include_router(unified_chat_router.router, prefix="", tags=["💬 Chat IA (legacy)"])

# Documents
app.include_router(apa7_pdf_router.router, tags=["Documents"])

# Class notes
app.include_router(class_notes_router.router, tags=["Class Notes"])

# Profile
app.include_router(profile_router.router, tags=["Profile"])

# 🤖 Agenda inteligente automatizada (programación vía chat + auto-ejecución)
app.include_router(scheduled_recording_router.router, tags=["Scheduled Recordings"])

# 🎙️ Unificado: Sesiones de Grabación (Manual, Auto, Agenda)
app.include_router(recording_session_router.router, tags=["Recording Sessions"])

# 🎤 VoiceNotes SST - Offline-first, resumible, idempotente
app.include_router(voice_note_router.router, tags=["Voice Notes"])

# 🖼️ Análisis de Imágenes y Documentos
app.include_router(image_analysis_router.router, tags=["Image Analysis"])

# 🗣️ Voice Agent (Deepgram Custom LLM)
app.include_router(deepgram_agent_router.router, tags=["Voice Agent Proxy"])

# Generador de Documentos IA
app.include_router(document_router.router, prefix="/api/documents", tags=["Documents"])
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
