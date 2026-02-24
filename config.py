"""
Configuración centralizada del Backend Súper IA
Versión: Production v4.0 - Ultra optimizado con 17 capacidades IA
Performance mejorado, caching inteligente y mejores defaults
Octubre 2025
"""

import os
from dotenv import load_dotenv
from datetime import timedelta

# Cargar variables de entorno
load_dotenv()

# =========================
# Configuración Principal
# =========================
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DEBUG = os.getenv("DEBUG", "false").lower() in ("true", "1", "t")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

if not SECRET_KEY and ENVIRONMENT == "production":
    raise ValueError("No se ha definido SECRET_KEY en el entorno de producción.")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# =========================
# Configuración de Base de Datos
# =========================
DATABASE_URL = os.getenv("DATABASE_URL")

# Fallback a SQLite para desarrollo local
if not DATABASE_URL and ENVIRONMENT == "development":
    DATABASE_URL = "sqlite:///./backend_super.db"

DATABASE_URL_SYNC = os.getenv("DATABASE_URL_SYNC")
if not DATABASE_URL_SYNC and ENVIRONMENT == "development":
    DATABASE_URL_SYNC = "sqlite:///./backend_super.db"

# =========================
# Configuración de Redis v4.0
# =========================
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "50"))  # 🚀 v4.0: Aumentado de 20 a 50
REDIS_SOCKET_KEEPALIVE = True  # 🚀 v4.0: Keep-alive para conexiones persistentes
REDIS_SOCKET_CONNECT_TIMEOUT = 5  # 🚀 v4.0: Timeout más agresivo
REDIS_DECODE_RESPONSES = False  # 🚀 v4.0: Mejor performance con bytes

# =========================
# Configuración de JWT
# =========================
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
ACCESS_TOKEN_EXPIRE_DELTA = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
JWT_EXPIRATION_MINUTES = ACCESS_TOKEN_EXPIRE_MINUTES
JWT_REFRESH_EXPIRATION_DAYS = int(os.getenv("JWT_REFRESH_EXPIRATION_DAYS", "7"))

# =========================
# Configuración de CORS
# =========================
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    if origin.strip()
] or ["*"]
CORS_CREDENTIALS = True
CORS_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
CORS_HEADERS = ["*"]

# =========================
# Configuración OAuth
# =========================
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET")
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID")
APPLE_CLIENT_SECRET = os.getenv("APPLE_CLIENT_SECRET")

# =========================
# Configuración de APIs Externas
# =========================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# =========================
# 🤖 Configuración de IA - ARQUITECTURA SEPARADA
# =========================
# Backend API y Modelos IA están en servidores DIFERENTES
# Backend: Railway/Render/Heroku (sin GPU)
# Modelos IA: RunPod/Vast.ai/Colab (con GPU)

USE_REMOTE_AI = os.getenv("USE_REMOTE_AI", "false").lower() in ("true", "1", "t")

# URL del servidor de IA (Ollama + modelos)
if USE_REMOTE_AI:
    # Producción: Servidor GPU remoto (RunPod/Vast.ai/Colab)
    AI_SERVER_URL = os.getenv("AI_SERVER_URL")  # REQUERIDO en producción
    if not AI_SERVER_URL and ENVIRONMENT == "production":
        raise ValueError("AI_SERVER_URL es requerido cuando USE_REMOTE_AI=true")
else:
    # Desarrollo: Ollama local para testing
    AI_SERVER_URL = os.getenv("AI_SERVER_URL", "http://localhost:11434")

AI_MODEL = os.getenv("AI_MODEL", "qwen2.5-omni:57b")  # Modelo principal
VISION_MODEL = os.getenv("VISION_MODEL", "qwen2.5-omni:57b")  # Mismo modelo (multimodal)
TEXT_MODEL = os.getenv("TEXT_MODEL", "qwen2.5-omni:57b")  # Mismo modelo

SEARXNG_URL = os.getenv("SEARXNG_URL", "")  # URL de SearXNG para LiveSearch (opcional)
LIVESEARCH_ENABLED = os.getenv("LIVESEARCH_ENABLED", "true").lower() in ("true", "1", "t")

# =========================
# 🎙️ Voice Processing Configuration
# =========================
# Voice modelos también corren en servidor GPU remoto (NO en backend)

# Si USE_REMOTE_AI = true, Whisper/TTS están en servidor GPU
# Si USE_REMOTE_AI = false, intentar local (desarrollo)
USE_LOCAL_WHISPER = os.getenv("USE_LOCAL_WHISPER", "false").lower() in ("true", "1", "t")
USE_LOCAL_TTS = os.getenv("USE_LOCAL_TTS", "false").lower() in ("true", "1", "t")

# Whisper Configuration
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3")  # Modelo en servidor GPU
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")  # cuda en servidor GPU

# Coqui TTS Configuration
COQUI_TTS_MODEL = os.getenv("COQUI_TTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2")
COQUI_TTS_DEVICE = os.getenv("COQUI_TTS_DEVICE", "cuda")  # cuda en servidor GPU

# APIs externas como FALLBACK (si servidor GPU no responde)
USE_WHISPER_API = os.getenv("USE_WHISPER_API", "false").lower() in ("true", "1", "t")
OPENAI_WHISPER_MODEL = os.getenv("OPENAI_WHISPER_MODEL", "whisper-1")

USE_ELEVENLABS_API = os.getenv("USE_ELEVENLABS_API", "false").lower() in ("true", "1", "t")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")

# =========================
# Storage Configuration
# =========================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# =========================
# Integraciones Externas v4.1 🔌
# =========================

# Slack Integration
SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID", "")
SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET", "")
SLACK_REDIRECT_URI = os.getenv("SLACK_REDIRECT_URI", "https://tu-dominio.com/api/slack/callback")

# Notion Integration
NOTION_CLIENT_ID = os.getenv("NOTION_CLIENT_ID", "")
NOTION_CLIENT_SECRET = os.getenv("NOTION_CLIENT_SECRET", "")
NOTION_REDIRECT_URI = os.getenv("NOTION_REDIRECT_URI", "https://tu-dominio.com/api/notion/callback")
NOTION_API_VERSION = "2022-06-28"

# GitHub Integration (ya existe, verificar)
# GITHUB_CLIENT_ID y GITHUB_CLIENT_SECRET ya definidos arriba en OAuth
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI", "https://tu-dominio.com/api/github/callback")

# Trello Integration
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY", "")
TRELLO_API_SECRET = os.getenv("TRELLO_API_SECRET", "")
TRELLO_REDIRECT_URI = os.getenv("TRELLO_REDIRECT_URI", "https://tu-dominio.com/api/trello/callback")

# Twilio Integration (SMS/WhatsApp)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "")

# Telegram Bot Integration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Microsoft 365 Integration (para futura implementación)
# MICROSOFT_CLIENT_ID y MICROSOFT_CLIENT_SECRET ya definidos arriba en OAuth
MICROSOFT_REDIRECT_URI = os.getenv("MICROSOFT_REDIRECT_URI", "https://tu-dominio.com/api/microsoft/callback")

# Twitter/X Integration (para futura implementación)
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET", "")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")

# LinkedIn Integration (para futura implementación)
LINKEDIN_CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID", "")
LINKEDIN_CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET", "")

# =========================
# Configuración de Métricas
# =========================
METRICS_ENABLED = os.getenv("METRICS_ENABLED", "true").lower() in ("true", "1", "t")
SENTRY_DSN = os.getenv("SENTRY_DSN")

# =========================
# Configuración de Rate Limiting v4.0
# =========================
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in ("true", "1", "t")
RATE_LIMIT_REQUESTS_PER_MINUTE = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "100"))  # 🚀 v4.0: 60 → 100
RATE_LIMIT_BURST_SIZE = int(os.getenv("RATE_LIMIT_BURST_SIZE", "20"))  # 🚀 v4.0: Permite bursts

# =========================
# Configuración de Vision Pipeline
# =========================
VISION_PIPELINE_ENABLED = os.getenv("VISION_PIPELINE_ENABLED", "true").lower() in ("true", "1", "t")
YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "yolov8n.pt")
OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "es,en").split(",")
VISION_MAX_FILE_SIZE_MB = int(os.getenv("VISION_MAX_FILE_SIZE_MB", "10"))
VISION_DEVICE = os.getenv("VISION_DEVICE", "auto")

# =========================
# Configuración de Storage
# =========================
STORAGE_TYPE = os.getenv("STORAGE_TYPE", "local")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
B2_APPLICATION_KEY_ID = os.getenv("B2_APPLICATION_KEY_ID")
B2_APPLICATION_KEY = os.getenv("B2_APPLICATION_KEY")
B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME")

# =========================
# Configuración de Hosts Permitidos
# =========================
ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "mi-backend-super.onrender.com",
    "api.miapp.com"
]

additional_hosts = os.getenv("ADDITIONAL_HOSTS", "")
if additional_hosts:
    ALLOWED_HOSTS.extend([host.strip() for host in additional_hosts.split(",") if host.strip()])

# =========================
# Feature Flags
# =========================
FEATURE_FLAGS = {
    "permissions_system": os.getenv("FEATURE_PERMISSIONS_SYSTEM", "true").lower() in ("true", "1", "t"),
    "vision_pipeline": VISION_PIPELINE_ENABLED,
    "semantic_search": os.getenv("FEATURE_SEMANTIC_SEARCH", "true").lower() in ("true", "1", "t"),
    "personal_agents": os.getenv("FEATURE_PERSONAL_AGENTS", "true").lower() in ("true", "1", "t"),
    "hybrid_chat": os.getenv("FEATURE_HYBRID_CHAT", "true").lower() in ("true", "1", "t"),
    "advanced_analytics": os.getenv("FEATURE_ANALYTICS", "true").lower() in ("true", "1", "t")
}

# =========================
# Información de la Aplicación v5.0 🔥
# =========================
APP_NAME = "Backend Súper IA v5.0 - 8x RTX A6000 Edition"
APP_VERSION = "5.0.0"
APP_DESCRIPTION = "Backend Enterprise - Qwen 2.5 Omni (multimodal), HunyuanVideo, Whisper Large-v3, Coqui XTTS-v2 - Arquitectura Distribuida"

# =========================
# Timeouts y Workers v4.0 - Optimizados
# =========================
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "45"))  # 🚀 v4.0: 30 → 45 para IA pesada
DATABASE_TIMEOUT_SECONDS = int(os.getenv("DATABASE_TIMEOUT_SECONDS", "15"))  # 🚀 v4.0: 10 → 15
EXTERNAL_API_TIMEOUT_SECONDS = int(os.getenv("EXTERNAL_API_TIMEOUT_SECONDS", "20"))  # 🚀 v4.0: 15 → 20
WORKER_CONNECTIONS = int(os.getenv("WORKER_CONNECTIONS", "2000"))  # 🚀 v4.0: 1000 → 2000
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "8"))  # 🚀 v4.0: 4 → 8 (más paralelismo)

# =========================
# Health Checks y Cache v4.0 - Optimizados
# =========================
HEALTH_CHECK_INTERVAL_SECONDS = int(os.getenv("HEALTH_CHECK_INTERVAL_SECONDS", "60"))  # 🚀 v4.0: 30 → 60 (menos overhead)
HEALTH_CHECK_TIMEOUT_SECONDS = int(os.getenv("HEALTH_CHECK_TIMEOUT_SECONDS", "3"))  # 🚀 v4.0: 5 → 3 (más rápido)
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "600"))  # 🚀 v4.0: 300 → 600 (10 min, mejor hit rate)
CACHE_MAX_SIZE = int(os.getenv("CACHE_MAX_SIZE", "5000"))  # 🚀 v4.0: 1000 → 5000 (más capacidad)
CACHE_COMPRESSION_ENABLED = os.getenv("CACHE_COMPRESSION_ENABLED", "true").lower() in ("true", "1", "t")  # 🚀 v4.0: Compresión

# =========================
# Server Configuration
# =========================
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

print(f"✅ Configuración cargada para entorno: {ENVIRONMENT}")
print(f"🚀 Backend API v6.0 - Arquitectura Distribuida")
print(f"🎯 Features habilitadas: {[k for k, v in FEATURE_FLAGS.items() if v]}")

if USE_REMOTE_AI:
    print(f"🤖 IA Remota: {AI_SERVER_URL}")
    print(f"📡 Modelo: {AI_MODEL}")
    print(f"💡 Arquitectura: Backend (sin GPU) → Servidor IA (con GPU)")
else:
    print(f"💻 IA Local: {AI_SERVER_URL} (solo desarrollo)")
    print(f"⚠️ Modo desarrollo: modelos locales ligeros")

if VISION_PIPELINE_ENABLED:
    print(f"�️ Vision Pipeline habilitado (device: {VISION_DEVICE})")

