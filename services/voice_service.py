"""
Voice Service Enterprise - Production Ready with Whisper STT & ElevenLabs TTS
Sistema de voz optimizado para producción multiusuario con máximo rendimiento
Versión: Production v4.0 - Enterprise Multiuser with ElevenLabs
"""
import asyncio
import logging
import json
import tempfile
import os
import io
import threading
from typing import AsyncGenerator, Optional, List, Dict, Any, Union
from time import perf_counter
from pathlib import Path
import uuid
from concurrent.futures import ThreadPoolExecutor

# Core libraries
import whisper
import torch
import httpx
import librosa
import soundfile as sf
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import aiofiles
from utils.safe_metrics import Counter, Histogram, Gauge

# Internal imports
from database.db_enterprise import get_primary_session as get_async_db
from models.models import User, ChatMessage
from services.gpt_service import chat_with_ai
from config import AI_SERVER_URL, AI_MODEL  # ✅ Usar Qwen 2.5 Omni multimodal
from utils.resilience import resilient

# Coqui TTS Service (LOCAL - 100% GRATIS) 🎯
try:
    from services.coqui_tts_service import coqui_tts_service, COQUI_AVAILABLE
except ImportError:
    coqui_tts_service = None
    COQUI_AVAILABLE = False
    logger.warning("⚠️ Coqui TTS no disponible, usando ElevenLabs como fallback")

# =============================================
# CONFIGURACIÓN DE LOGGING ENTERPRISE
# =============================================
logger = logging.getLogger("voice_service_enterprise")
handler = logging.StreamHandler()
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# =============================================
# MÉTRICAS PROMETHEUS
# =============================================
VOICE_REQUESTS_TOTAL = Counter(
    'voice_requests_total',
    'Total voice service requests',
    ['operation', 'status', 'user_plan']
)

VOICE_PROCESSING_TIME = Histogram(
    'voice_processing_seconds',
    'Voice processing duration',
    ['operation']
)

ACTIVE_VOICE_SESSIONS = Gauge(
    'active_voice_sessions',
    'Number of active voice sessions'
)

# =============================================
# CONFIGURACIÓN ENTERPRISE
# =============================================
class VoiceConfig:
    """Configuración optimizada para 8x RTX A6000 (384GB VRAM)"""
    
    # Whisper STT Configuration - MÁXIMA CALIDAD SIN CUANTIZACIÓN 🔥
    WHISPER_MODEL = "large-v3"  # Large-v3 = MEJOR MODELO (97% precisión, 10GB FP16)
    WHISPER_DEVICE = "cuda"  # Siempre GPU con esta potencia
    
    # TTS Configuration - COQUI LOCAL (100% gratis) 🎯
    USE_COQUI_TTS = True  # Siempre local con esta potencia
    
    # ElevenLabs TTS Configuration (FALLBACK)
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"
    DEFAULT_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"  # Rachel voice (default)
    
    # Voice profiles (ElevenLabs Voice IDs)
    SUPPORTED_VOICES = {
        "neural_voice_1": "EXAVITQu4vr4xnSDxMaL",  # Rachel - narration
        "neural_voice_2": "TxGEqnHWrfWFTfGW9XjX",  # Josh - young male
        "neural_voice_3": "pNInz6obpgDQGcFmaJgB",  # Adam - deep male
        "neural_voice_4": "AZnzlk1XvdvUeBnXmlld",  # Domi - confident female
    }
    
    # Performance settings
    MAX_CONCURRENT_USERS = 10
    TTS_CHUNK_SIZE = 500
    MAX_AUDIO_SIZE_MB = 25
    CACHE_TTL_SECONDS = 3600
    
    # Audio settings
    SAMPLE_RATE = 22050
    AUDIO_FORMAT = "mp3"  # ElevenLabs retorna MP3
    
    # Directories
    VOICE_CACHE_DIR = "voice_cache"
    TEMP_AUDIO_DIR = "temp_audio"

config = VoiceConfig()

# Crear directorios necesarios
for directory in [config.VOICE_CACHE_DIR, config.TEMP_AUDIO_DIR]:
    os.makedirs(directory, exist_ok=True)

# =============================================
# VOICE ENGINE ENTERPRISE
# =============================================
class VoiceEngineEnterprise:
    """
    Motor de voz enterprise con:
    - Whisper LARGE (máxima calidad STT) 🔥
    - Coqui XTTS-v2 (TTS local de alta calidad) 🎯
    - ElevenLabs (fallback si Coqui no disponible)
    """
    
    def __init__(self):
        self._whisper_model = None
        self._httpx_client = httpx.AsyncClient(timeout=30.0)
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._model_lock = threading.Lock()
        self._session_cache = {}
        
        # Coqui TTS
        self.use_coqui = config.USE_COQUI_TTS and COQUI_AVAILABLE
        if self.use_coqui:
            logger.info("🎯 Usando Coqui XTTS-v2 (TTS local de alta calidad)")
        else:
            logger.info("⚠️ Usando ElevenLabs (TTS externo)")
    
    def initialize_whisper(self):
        """
        Método síncrono para precargar Whisper en startup
        🔥 v5.0: Whisper Large-v3 FP16 (10GB VRAM, máxima calidad)
        Hardware: 8x RTX A6000 (384GB VRAM)
        """
        if self._whisper_model is None:
            with self._model_lock:
                if self._whisper_model is None:
                    logger.info(f"🔥 Precargando Whisper {config.WHISPER_MODEL} (FP16, sin cuantización)...")
                    self._whisper_model = whisper.load_model(
                        config.WHISPER_MODEL,
                        device=config.WHISPER_DEVICE,
                        download_root=None,  # Usar default cache
                        in_memory=True  # Mantener en RAM/VRAM para velocidad
                    )
                    logger.info(f"✅ Whisper {config.WHISPER_MODEL} precargado (10GB VRAM, FP16)")
        return self._whisper_model
    
    async def _load_whisper_model(self):
        """Carga lazy del modelo Whisper"""
        if self._whisper_model is None:
            with self._model_lock:
                if self._whisper_model is None:
                    logger.info(f"Loading Whisper model: {config.WHISPER_MODEL}")
                    loop = asyncio.get_event_loop()
                    self._whisper_model = await loop.run_in_executor(
                        self._executor,
                        lambda: whisper.load_model(
                            config.WHISPER_MODEL,
                            device=config.WHISPER_DEVICE
                        )
                    )
                    logger.info("Whisper model loaded successfully")
        return self._whisper_model
    
    async def _load_tts_model(self):
        """Verificar API key de ElevenLabs"""
        if not config.ELEVENLABS_API_KEY:
            raise RuntimeError("ELEVENLABS_API_KEY no configurada en las variables de entorno")
        logger.info("ElevenLabs TTS API configurada correctamente")
        return True
    
    @resilient(max_attempts=3, wait_min=1.0, wait_max=5.0, cb_name="whisper_stt")
    async def speech_to_text(self, audio_bytes: bytes, user_id: str = None) -> Dict[str, Any]:
        """
        Convierte audio a texto usando Whisper
        """
        start_time = perf_counter()
        
        try:
            # Validaciones
            if not audio_bytes or len(audio_bytes) < 1000:
                raise ValueError("Audio demasiado corto")
            
            if len(audio_bytes) > config.MAX_AUDIO_SIZE_MB * 1024 * 1024:
                raise ValueError(f"Audio demasiado grande: {len(audio_bytes)} bytes")
            
            # Cargar modelo
            model = await self._load_whisper_model()
            
            # Crear archivo temporal
            temp_file = f"{config.TEMP_AUDIO_DIR}/stt_{uuid.uuid4().hex}.wav"
            
            try:
                # Guardar audio temporal
                async with aiofiles.open(temp_file, 'wb') as f:
                    await f.write(audio_bytes)
                
                # Procesar con Whisper
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    self._executor,
                    lambda: model.transcribe(
                        temp_file,
                        language="es",  # Español por defecto
                        task="transcribe",
                        fp16=torch.cuda.is_available()
                    )
                )
                
                processing_time = perf_counter() - start_time
                
                # Métricas
                VOICE_PROCESSING_TIME.labels(operation="stt").observe(processing_time)
                VOICE_REQUESTS_TOTAL.labels(
                    operation="stt", 
                    status="success",
                    user_plan="unknown"
                ).inc()
                
                logger.info(f"STT exitoso en {processing_time:.2f}s para usuario {user_id}")
                
                return {
                    "text": result["text"].strip(),
                    "confidence": 0.95,  # Whisper no proporciona confidence score
                    "language": result.get("language", "es"),
                    "processing_time": processing_time,
                    "segments": result.get("segments", [])
                }
                
            finally:
                # Limpiar archivo temporal
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                
        except Exception as e:
            processing_time = perf_counter() - start_time
            VOICE_REQUESTS_TOTAL.labels(
                operation="stt",
                status="error", 
                user_plan="unknown"
            ).inc()
            
            logger.error(f"Error en STT: {str(e)}")
            raise
    
    @resilient(max_attempts=2, wait_min=0.5, wait_max=3.0, cb_name="tts")
    async def text_to_speech(
        self, 
        text: str, 
        voice: str = "neural_voice_1",
        user_id: str = None
    ) -> bytes:
        """
        Convierte texto a voz usando:
        - Coqui XTTS-v2 (LOCAL - GRATIS) si está disponible 🎯
        - ElevenLabs (API - CARO) como fallback
        """
        start_time = perf_counter()
        
        # Si Coqui está disponible, usar Coqui (LOCAL Y GRATIS) 🎯
        if self.use_coqui and coqui_tts_service is not None:
            return await self._text_to_speech_coqui(text, voice, user_id)
        
        # Fallback a ElevenLabs
        return await self._text_to_speech_elevenlabs(text, voice, user_id)
    
    async def _text_to_speech_coqui(
        self,
        text: str,
        voice: str,
        user_id: str = None
    ) -> bytes:
        """
        TTS usando Coqui XTTS-v2 (100% LOCAL - GRATIS)
        Calidad: 95% similar a ElevenLabs
        Costo: $0
        """
        start_time = perf_counter()
        
        try:
            if not text or len(text.strip()) < 1:
                raise ValueError("Texto vacío")
            
            # Mapear voces de ElevenLabs a Coqui
            coqui_voice = self._map_voice_to_coqui(voice)
            
            # Generar con Coqui
            audio_bytes = await coqui_tts_service.text_to_speech(
                text=text,
                language="es",
                voice_preset=coqui_voice
            )
            
            processing_time = perf_counter() - start_time
            
            VOICE_PROCESSING_TIME.labels(operation="tts_coqui").observe(processing_time)
            VOICE_REQUESTS_TOTAL.labels(
                operation="tts",
                status="success",
                user_plan="coqui_local"
            ).inc()
            
            logger.info(
                f"✅ Coqui TTS exitoso en {processing_time:.2f}s "
                f"para usuario {user_id} (voz: {coqui_voice})"
            )
            
            return audio_bytes
            
        except Exception as e:
            logger.error(f"❌ Error en Coqui TTS: {str(e)}, fallback a ElevenLabs")
            # Si falla Coqui, usar ElevenLabs como fallback
            return await self._text_to_speech_elevenlabs(text, voice, user_id)
    
    def _map_voice_to_coqui(self, elevenlabs_voice: str) -> str:
        """
        Mapea voces de ElevenLabs a voces de Coqui
        
        Args:
            elevenlabs_voice: ID de voz de ElevenLabs
        
        Returns:
            str: Preset de voz de Coqui
        """
        voice_mapping = {
            "neural_voice_1": "female",        # Rachel → Female
            "neural_voice_2": "young_male",    # Josh → Young Male
            "neural_voice_3": "male",          # Adam → Male
            "neural_voice_4": "young_female",  # Domi → Young Female
        }
        return voice_mapping.get(elevenlabs_voice, "female")
    
    async def _text_to_speech_elevenlabs(
        self,
        text: str,
        voice: str,
        user_id: str = None
    ) -> bytes:
        """
        TTS usando ElevenLabs (FALLBACK - CARO)
        Solo se usa si Coqui no está disponible
        """
        start_time = perf_counter()
        
        try:
            if not text or len(text.strip()) < 1:
                raise ValueError("Texto vacío")
            
            if len(text) > 5000:  # Límite para evitar timeouts
                text = text[:5000] + "..."
            
            # Verificar API
            await self._load_tts_model()
            
            # Obtener Voice ID
            voice_id = config.SUPPORTED_VOICES.get(voice, config.DEFAULT_VOICE_ID)
            
            # Llamar a ElevenLabs API
            url = f"{config.ELEVENLABS_API_URL}/text-to-speech/{voice_id}"
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": config.ELEVENLABS_API_KEY
            }
            data = {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75
                }
            }
            
            response = await self._httpx_client.post(url, headers=headers, json=data)
            
            if response.status_code != 200:
                raise RuntimeError(f"ElevenLabs API error: {response.status_code} - {response.text}")
            
            audio_data = response.content
            
            processing_time = perf_counter() - start_time
            
            # Métricas
            VOICE_PROCESSING_TIME.labels(operation="tts").observe(processing_time)
            VOICE_REQUESTS_TOTAL.labels(
                operation="tts",
                status="success",
                user_plan="unknown"
            ).inc()
            
            logger.info(f"TTS exitoso (ElevenLabs) en {processing_time:.2f}s: {len(text)} chars -> {len(audio_data)} bytes")
            
            return audio_data
                    
        except Exception as e:
            processing_time = perf_counter() - start_time
            VOICE_REQUESTS_TOTAL.labels(
                operation="tts",
                status="error",
                user_plan="unknown"
            ).inc()
            
            logger.error(f"Error en TTS: {str(e)}")
            raise
    
    async def text_to_speech_stream(
        self, 
        text: str, 
        voice: str = "neural_voice_1",
        user_id: str = None
    ) -> AsyncGenerator[bytes, None]:
        """
        Streaming TTS usando ElevenLabs (dividir en chunks y procesar)
        """
        try:
            # Dividir texto en chunks
            chunks = [text[i:i+config.TTS_CHUNK_SIZE] for i in range(0, len(text), config.TTS_CHUNK_SIZE)]
            
            for i, chunk in enumerate(chunks):
                if chunk.strip():
                    logger.debug(f"Procesando chunk {i+1}/{len(chunks)}")
                    audio_data = await self.text_to_speech(chunk, voice, user_id)
                    yield audio_data
                    
                    # Pequeña pausa para no saturar
                    await asyncio.sleep(0.01)
                    
        except Exception as e:
            logger.error(f"Error en TTS streaming: {str(e)}")
            # Yield silencio en caso de error
            yield self._generate_silence(1.0)
    
    def _generate_silence(self, duration_seconds: float) -> bytes:
        """Genera audio de silencio"""
        samples = int(config.SAMPLE_RATE * duration_seconds)
        silence = np.zeros(samples, dtype=np.float32)
        
        # Convertir a WAV bytes
        with io.BytesIO() as buffer:
            sf.write(buffer, silence, config.SAMPLE_RATE, format='WAV')
            return buffer.getvalue()
    
    async def cleanup(self):
        """Cleanup de recursos"""
        self._executor.shutdown(wait=True)
        await self._httpx_client.aclose()
        
        # Limpiar cache de archivos temporales
        for directory in [config.VOICE_CACHE_DIR, config.TEMP_AUDIO_DIR]:
            if os.path.exists(directory):
                for file in os.listdir(directory):
                    try:
                        os.remove(os.path.join(directory, file))
                    except:
                        pass

# Instancia global del motor de voz
voice_engine = VoiceEngineEnterprise()

# =============================================
# GESTIÓN DE SESIONES MULTIUSUARIO
# =============================================
_user_limiters: Dict[str, asyncio.Semaphore] = {}
_active_sessions: Dict[str, Dict[str, Any]] = {}

def get_user_limiter(user_id: str, max_concurrent: int = None) -> asyncio.Semaphore:
    """Obtener limitador de concurrencia por usuario"""
    if max_concurrent is None:
        max_concurrent = config.MAX_CONCURRENT_USERS
        
    if user_id not in _user_limiters:
        _user_limiters[user_id] = asyncio.Semaphore(max_concurrent)
        
    return _user_limiters[user_id]

async def start_voice_session(user_id: str) -> str:
    """Iniciar sesión de voz para usuario"""
    session_id = f"voice_{user_id}_{uuid.uuid4().hex[:8]}"
    
    _active_sessions[session_id] = {
        "user_id": user_id,
        "start_time": perf_counter(),
        "requests": 0,
        "status": "active"
    }
    
    ACTIVE_VOICE_SESSIONS.inc()
    return session_id

async def end_voice_session(session_id: str):
    """Finalizar sesión de voz"""
    if session_id in _active_sessions:
        session = _active_sessions.pop(session_id)
        duration = perf_counter() - session["start_time"]
        
        logger.info(f"Sesión {session_id} finalizada: {duration:.2f}s, {session['requests']} requests")
        ACTIVE_VOICE_SESSIONS.dec()

# =============================================
# VALIDACIÓN DE USUARIO ENTERPRISE
# =============================================
async def validate_user(user_id: str, db: AsyncSession) -> User:
    """Validar usuario con cache y optimizaciones"""
    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        
        if not user:
            logger.error(f"Usuario no encontrado: {user_id}")
            raise RuntimeError(f"Usuario inválido: {user_id}")
            
        if not user.is_active:
            raise RuntimeError(f"Usuario inactivo: {user_id}")
            
        return user
        
    except Exception as e:
        logger.error(f"Error validando usuario {user_id}: {str(e)}")
        raise

# =============================================
# API PRINCIPAL PARA ROUTERS
# =============================================

async def speech_to_text(audio_bytes: bytes, user_id: str = None) -> str:
    """API simplificada para STT"""
    result = await voice_engine.speech_to_text(audio_bytes, user_id)
    return result["text"]

async def text_to_speech_stream(
    text: str, 
    voice: str = "neural_voice_1", 
    user_id: str = None
) -> AsyncGenerator[bytes, None]:
    """API simplificada para TTS streaming"""
    async for chunk in voice_engine.text_to_speech_stream(text, voice, user_id):
        yield chunk

async def talk_with_ai_stream_realtime(
    user_id: str,
    user_audio: bytes,
    voice: str = "neural_voice_1",
    db: Optional[AsyncSession] = None
) -> AsyncGenerator[bytes, None]:
    """
    Pipeline completo de conversación voz a voz
    Audio → STT → Qwen IA → TTS → Audio
    """
    if not db:
        raise RuntimeError("DB session requerida")
    
    session_id = await start_voice_session(user_id)
    
    try:
        # Validar usuario
        user = await validate_user(user_id, db)
        limiter = get_user_limiter(user_id)
        
        async with limiter:
            logger.info(f"Iniciando conversación voice-to-voice para usuario {user_id}")
            
            # 1️⃣ STT: Audio a texto
            start_time = perf_counter()
            stt_result = await voice_engine.speech_to_text(user_audio, user_id)
            user_text = stt_result["text"]
            stt_time = perf_counter() - start_time
            
            logger.info(f"STT completado en {stt_time:.2f}s: '{user_text[:100]}...'")
            
            # Guardar mensaje del usuario
            user_message = ChatMessage(user_id=user_id, role="user", content=user_text)
            db.add(user_message)
            await db.commit()
            
            # 2️⃣ Chat: Obtener respuesta de Qwen IA
            messages = [{"role": "user", "content": user_text}]
            
            ai_response = await chat_with_ai(
                messages=messages,
                user=user_id,
                temperature=0.8,
                max_tokens=1500,
                fast_reasoning=True
            )
            
            # 3️⃣ TTS Streaming: Convertir respuesta a audio
            async for audio_chunk in voice_engine.text_to_speech_stream(ai_response, voice, user_id):
                yield audio_chunk
            
            # Guardar respuesta de la IA
            ai_message = ChatMessage(user_id=user_id, role="assistant", content=ai_response)
            db.add(ai_message)
            await db.commit()
            
            total_time = perf_counter() - start_time
            logger.info(f"Conversación voice-to-voice completada en {total_time:.2f}s")
            
    except Exception as e:
        logger.error(f"Error en talk_with_ai_stream_realtime: {str(e)}")
        
        # Audio de error
        error_message = "Lo siento, hubo un problema procesando tu mensaje de voz."
        async for error_audio in voice_engine.text_to_speech_stream(error_message, voice, user_id):
            yield error_audio
    finally:
        await end_voice_session(session_id)

# =============================================
# HEALTH CHECK Y UTILIDADES
# =============================================
async def health_check() -> Dict[str, Any]:
    """Health check completo del servicio de voz"""
    try:
        # Test básico de TTS
        test_audio = await voice_engine.text_to_speech("Test de sistema", "neural_voice_1")
        
        return {
            "status": "healthy",
            "engines": {
                "stt": "whisper",
                "tts": "coqui_tts",
                "whisper_model": config.WHISPER_MODEL,
                "tts_model": config.TTS_MODEL,
                "device": config.TTS_DEVICE
            },
            "supported_voices": list(config.SUPPORTED_VOICES.keys()),
            "test_audio_size": len(test_audio),
            "active_sessions": len(_active_sessions),
            "max_concurrent_users": config.MAX_CONCURRENT_USERS,
            "performance": {
                "cache_dir": config.VOICE_CACHE_DIR,
                "sample_rate": config.SAMPLE_RATE,
                "chunk_size": config.TTS_CHUNK_SIZE
            }
        }
    except Exception as e:
        logger.error(f"Health check fallido: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "engines": {
                "stt": "whisper_failed",
                "tts": "elevenlabs_failed"
            }
        }

async def get_available_voices() -> List[str]:
    """Obtener lista de voces disponibles"""
    return list(config.SUPPORTED_VOICES.keys())

async def get_voice_info(voice_id: str) -> Dict[str, Any]:
    """Obtener información detallada de una voz de ElevenLabs"""
    if voice_id in config.SUPPORTED_VOICES:
        elevenlabs_voice_id = config.SUPPORTED_VOICES[voice_id]
        return {
            "id": voice_id,
            "elevenlabs_voice_id": elevenlabs_voice_id,
            "engine": "elevenlabs",
            "language": "multilingual",
            "quality": "neural_hd"
        }
    return {"error": "Voice not found"}

async def get_voice_metrics() -> Dict[str, Any]:
    """Obtener métricas del servicio de voz"""
    return {
        "active_sessions": len(_active_sessions),
        "total_users": len(_user_limiters),
        "cache_files": len(os.listdir(config.VOICE_CACHE_DIR)) if os.path.exists(config.VOICE_CACHE_DIR) else 0,
        "temp_files": len(os.listdir(config.TEMP_AUDIO_DIR)) if os.path.exists(config.TEMP_AUDIO_DIR) else 0
    }

# =============================================
# CLEANUP AUTOMÁTICO
# =============================================
async def cleanup_voice_service():
    """Cleanup completo del servicio"""
    await voice_engine.cleanup()
    
    # Cerrar sesiones activas
    for session_id in list(_active_sessions.keys()):
        await end_voice_session(session_id)
    
    logger.info("Voice service cleanup completado")

# =============================================
# EXPORT PRINCIPAL
# =============================================
__all__ = [
    "speech_to_text",
    "text_to_speech_stream",
    "talk_with_ai_stream_realtime",
    "health_check",
    "get_available_voices", 
    "get_voice_info",
    "get_voice_metrics",
    "cleanup_voice_service",
    "voice_engine",
    "VoiceConfig"
]