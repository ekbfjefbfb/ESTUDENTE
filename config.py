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
if ENVIRONMENT == "production" and SECRET_KEY == "dev-secret-key-change-in-production":
    raise ValueError("SECRET_KEY no puede usar el valor por defecto en producción.")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# =========================
# Configuración de Base de Datos (Nhost PostgreSQL)
# =========================
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "❌ DATABASE_URL no está definido. "
        "Configura la URL de Nhost PostgreSQL en las variables de entorno."
    )

DATABASE_URL_SYNC = os.getenv("DATABASE_URL_SYNC", DATABASE_URL)

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
def _resolve_cors_origins() -> list[str]:
    raw_origins = str(os.getenv("CORS_ORIGINS", "")).strip()
    if raw_origins:
        origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
        if origins:
            return origins

    return [
        "http://localhost",
        "http://localhost:3000",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
        "http://testserver",
    ]


CORS_ORIGINS = _resolve_cors_origins()
CORS_CREDENTIALS = os.getenv("CORS_CREDENTIALS", "true").lower() in ("true", "1", "t")
if "*" in CORS_ORIGINS or not CORS_ORIGINS:
    CORS_CREDENTIALS = False
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
# 🤖 GROQ AI MODEL REGISTRY - v6.0
# Selección lógica y honesta de modelos
# =========================

# API Key
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

# --- MODELO FAST: USO GENERAL (~20B parámetros) ---
# CASOS DE USO:
# - Chat diario, respuestas cortas
# - Saludos, tareas simples, preguntas directas
# - Respuestas < 3 líneas
# - Mayor velocidad, menor costo
# - 80% de las peticiones van aquí
GROQ_MODEL_FAST = os.getenv(
    "GROQ_MODEL_FAST",
    "llama-3.3-70b-versatile"  # Llama 3.3 70B, ultra potente y rápido
).strip()

# --- MODELO REASONING: RAZONAMIENTO COMPLEJO (~120B parámetros) ---
# CASOS DE USO:
# - Explicaciones profundas y detalladas
# - Código, debugging, arquitectura
# - Resúmenes complejos, análisis académicos
# - Tesis, ensayos, investigación
# - Cuando el usuario pide "explicame", "detalle", "por qué"
# - Mensajes largos (>800 chars) o con código
GROQ_MODEL_REASONING = os.getenv(
    "GROQ_MODEL_REASONING",
    "qwen/qwen3-32b"  # Qwen 3 32B, razonamiento profundo
).strip()

# Esfuerzo de razonamiento: low | medium | high
# Afecta cuánto "piensa" el modelo antes de responder
GROQ_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "default").strip()

# --- MODELO VISION: ANÁLISIS DE IMÁGENES (Meta/Llama) ---
# CASOS DE USO:
# - Describir imágenes enviadas por el usuario
# - Analizar documentos escaneados (PDFs como imágenes)
# - Reconocer texto en imágenes (OCR visual)
# - Interpretar gráficos, diagramas, fotos
GROQ_MODEL_VISION = os.getenv(
    "GROQ_MODEL_VISION",
    "meta-llama/llama-4-scout-17b-16e-instruct"  # Meta/Llama 4 con visión (Scout)
).strip()

# --- LÍMITES DE TOKENS ---
# Máximo tokens en respuesta para cada tipo
GROQ_MAX_TOKENS_FAST = int(os.getenv("GROQ_MAX_TOKENS_FAST", "1024"))      # Respuestas cortas
GROQ_MAX_TOKENS_REASONING = 4096  # Qwen 3 razonamiento profundo
GROQ_MAX_TOKENS_VISION = int(os.getenv("GROQ_MAX_TOKENS_VISION", "1024")) # Descripción de imágenes

# --- PARÁMETROS IA ---
TEMPERATURE_REASONING = 0.6  # Qwen 3 precisión
TOP_P = 0.95  # Qwen 3 balanceado
REASONING_EFFORT = "default" # Qwen 3 esfuerzo

# --- SYSTEM PROMPT BASE ---
# Este prompt se añade a TODAS las conversaciones
GROQ_SYSTEM_PROMPT = os.getenv(
    "GROQ_SYSTEM_PROMPT",
    """Eres la extensión cognitiva del usuario: piensas con él/ella, no le callas la boca.

Prioridad: que se sienta comprendido/a antes que sonar “corporativo”. Puedes saludar o reconocer el tono del mensaje cuando ayude a la confianza; evita solo el relleno vacío o frases de manual.

Cómo responder:
• Escucha de verdad: reformula en una frase lo que entendiste cuando importe (duda, estrés, alegría).
• Sé claro y útil: **negritas** o viñetas cuando ordenen la respuesta.
• Si no sabes algo, dilo sin dramatizar y ofrece lo que sí puedas aportar.
• Si la intención es obvia, actúa (ej. agenda, resumen) sin pedir permiso para cada coma.
• Hechos y cifras: no inventes ni “rellenes” lagunas; si no hay dato fiable, dilo claro.
• Personalidad y Emojis: utiliza emojis de forma creativa y variada según el contexto de la situación para reforzar la empatía, el tono o el tema de la conversación (ej. si hablas de éxito usa uno festivo, si es algo serio sé más sobrio, si es aprendizaje usa algo académico). Que se sienta natural, no mecánico."""
).strip()

# Permite que el modelo invoque la herramienta search_web (Tavily/Serper) cuando no hubo prefetch
GROQ_CHAT_WEB_TOOLS = os.getenv("GROQ_CHAT_WEB_TOOLS", "true").lower() in ("true", "1", "t")

# Multi-turn search_web: rondas máx. Groq↔tools y llamadas search_web por petición HTTP (anti abuso, multiusuario)
GROQ_TOOL_SEARCH_MAX_ROUNDS = max(1, int(os.getenv("GROQ_TOOL_SEARCH_MAX_ROUNDS", "5")))
GROQ_TOOL_SEARCH_MAX_CALLS = max(1, int(os.getenv("GROQ_TOOL_SEARCH_MAX_CALLS", "10")))

# Concurrencia global hacia Tavily/Serper (evita saturar APIs en picos de carga)
GROQ_SEARCH_API_MAX_CONCURRENT = max(1, int(os.getenv("GROQ_SEARCH_API_MAX_CONCURRENT", "40")))


# =========================
# 🎯 HELPERS DE SELECCIÓN DE MODELO
# =========================

def select_groq_model(message_text: str, has_images: bool = False) -> str:
    """
    Selecciona el modelo de Groq más apropiado basado en el mensaje.
    
    LÓGICA DE SELECCIÓN:
    1. Si hay imágenes → VISION (único que soporta imágenes)
    2. Si es complejo → REASONING (120B)
    3. Default → FAST (20B) - 80% de casos
    """
    if has_images:
        return GROQ_MODEL_VISION
    
    if _is_complex_request(message_text):
        return GROQ_MODEL_REASONING
    
    return GROQ_MODEL_FAST


def _is_complex_request(text: str) -> bool:
    """
    Detecta si una petición requiere razonamiento profundo.
    
    INDICADORES DE COMPLEJIDAD:
    - Mensaje largo (>800 chars)
    - Palabras clave técnicas/académicas
    - Código en el mensaje
    """
    if not text:
        return False
    
    text_lower = text.lower()
    
    # 1. Mensajes largos = más contexto = más razonamiento
    if len(text) >= 800:
        return True
    
    # 2. Marcadores de peticiones profundas
    complex_markers = (
        # Explicaciones
        "explica", "explicame", "explícame", "detall", "profund",
        "paso a paso", "cómo funciona", "como funciona",
        "por qué", "por que", "porqué",
        
        # Académico
        "tesis", "ensayo", "investigación", "investigacion",
        "análisis", "analisis", "conclusión", "conclusion",
        "resumen", "resume", "sintetiza",
        "teoría", "teoria", "marco teórico",
        
        # Código/Técnico
        "código", "codigo", "programa", "debug", "error",
        "optimiza", "arquitectura", "refactor", "diseño",
        "performance", "latencia", "database", "sql",
        "websocket", "api", "docker", "kubernetes",
    )
    
    if any(marker in text_lower for marker in complex_markers):
        return True
    
    # 3. Detectar código (bloques markdown o sintaxis Python)
    if "```" in text or "\ndef " in text or "\nclass " in text:
        return True
    
    return False


def get_max_tokens_for_model(model: str) -> int:
    """Retorna el límite de tokens apropiado para cada modelo."""
    if model == GROQ_MODEL_VISION:
        return GROQ_MAX_TOKENS_VISION
    if model == GROQ_MODEL_REASONING:
        return GROQ_MAX_TOKENS_REASONING
    return GROQ_MAX_TOKENS_FAST


# Legacy aliases for backwards compatibility
GROQ_LLM_FAST_MODEL = GROQ_MODEL_FAST
GROQ_LLM_REASONING_MODEL = GROQ_MODEL_REASONING
GROQ_LLM_REASONING_EFFORT = GROQ_REASONING_EFFORT
GROQ_MAX_COMPLETION_TOKENS = GROQ_MAX_TOKENS_FAST
GROQ_MAX_COMPLETION_TOKENS_COMPLEX = GROQ_MAX_TOKENS_REASONING


# =========================
# 🤖 Configuración de IA - ARQUITECTURA GROQ-ONLY
# =========================
USE_REMOTE_AI = True  # Siempre True - usamos Groq API externa
AI_SERVER_URL = os.getenv("AI_SERVER_URL", "https://api.groq.com").strip() or "https://api.groq.com"
AI_MODEL = os.getenv("AI_MODEL", "auto").strip() or "auto"  # auto = usa select_groq_model()
VISION_MODEL = os.getenv("VISION_MODEL", "").strip() or None
TEXT_MODEL = os.getenv("TEXT_MODEL", "").strip() or None
GROQ_VISION_MODEL = os.getenv(
    "GROQ_VISION_MODEL",
    GROQ_MODEL_VISION
).strip()

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
    "estudente.onrender.com",
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
# Información de la Aplicación v5.0
# =========================
APP_NAME = "Backend Súper IA v5.0"
APP_VERSION = "5.0.0"
APP_DESCRIPTION = "Backend Enterprise - Groq"

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
    print(f"🤖 IA: Groq Cloud API")
    print(f"📡 Endpoint: {AI_SERVER_URL}")
    print(f"� Modelo: {AI_MODEL} (fast/reasoning según complejidad)")
    print(f"🎯 Arquitectura: Backend → Groq API")
else:
    print(f"💻 IA Local: {AI_SERVER_URL} (solo desarrollo)")
    print(f"⚠️ Modo desarrollo: modelos locales ligeros")

if VISION_PIPELINE_ENABLED:
    print(f"�️ Vision Pipeline habilitado (device: {VISION_DEVICE})")
