from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import wave
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger("groq_voice_service")

# --- RESILIENCE CONFIG ---
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1.0  # seconds
TIMEOUT_SECONDS = 30.0

# --- CIRCUIT BREAKER & RATE LIMITER ---
class GroqSTTRateLimiter:
    """Rate limiter para Groq STT - evita 429 errors"""
    def __init__(self, max_requests_per_minute: int = 20):
        self.max_requests = max_requests_per_minute
        self.requests: List[float] = []
        self.circuit_open = False
        self.circuit_open_until: float = 0
        self.lock = asyncio.Lock()
    
    async def acquire(self) -> bool:
        """Intenta adquirir permiso para hacer request. Retorna False si debe esperar."""
        async with self.lock:
            now = asyncio.get_event_loop().time()
            
            # Circuit breaker abierto?
            if self.circuit_open:
                if now < self.circuit_open_until:
                    return False
                self.circuit_open = False
                logger.info("Circuit breaker closed - resuming STT requests")
            
            # Limpiar requests antiguos (> 60 segundos)
            self.requests = [t for t in self.requests if now - t < 60]
            
            # Check rate limit
            if len(self.requests) >= self.max_requests:
                wait_time = 60 - (now - self.requests[0])
                logger.warning(f"STT rate limit reached. Waiting {wait_time:.1f}s")
                return False
            
            self.requests.append(now)
            return True
    
    def record_error(self, status_code: int):
        """Registra error para circuit breaker"""
        if status_code == 429:
            self.circuit_open = True
            self.circuit_open_until = asyncio.get_event_loop().time() + 30  # 30s cooldown
            logger.warning("Circuit breaker OPEN - too many 429 errors")

# Instancia global del rate limiter
_stt_rate_limiter = GroqSTTRateLimiter(max_requests_per_minute=15)


# =========================
# ElevenLabs TTS Configuration
# =========================
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2").strip()
ELEVENLABS_VOICE = os.getenv("ELEVENLABS_VOICE", "Antoni").strip()  # Buena para español
ELEVENLABS_STABILITY = float(os.getenv("ELEVENLABS_STABILITY", "0.5"))
ELEVENLABS_SIMILARITY_BOOST = float(os.getenv("ELEVENLABS_SIMILARITY_BOOST", "0.75"))
USE_ELEVENLABS_API = os.getenv("USE_ELEVENLABS_API", "true").lower() in ("true", "1", "t")


def _should_use_elevenlabs(text: str, language: Optional[str] = None) -> bool:
    """Decide si usar ElevenLabs (prioridad para español) o Groq TTS."""
    if not USE_ELEVENLABS_API or not ELEVENLABS_API_KEY:
        return False
    
    # Si el idioma es español explícitamente, siempre usar ElevenLabs
    if language and language.lower() in ("es", "spa", "spanish", "es-es", "es-mx"):
        return True
    
    # Detección más agresiva de español para asegurar ElevenLabs
    spanish_markers = ["ñ", "á", "é", "í", "ó", "ú", "ü", "¿", "¡", "hola", "qué", "estás", "estudiante"]
    text_lower = text.lower()
    
    # Si contiene cualquier marcador o es suficientemente largo (más de 10 chars) 
    # y no parece ser puramente código/inglés técnico, preferir ElevenLabs
    if any(marker in text_lower for marker in spanish_markers):
        return True
        
    # Por defecto, si no hay marcadores claros pero es texto narrativo largo, preferir ElevenLabs
    if len(text_lower) > 20 and not text_lower.startswith("{"):
        return True

    return False


async def _post_with_retry(
    url: str,
    headers: Dict[str, str],
    json_data: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    timeout: float = TIMEOUT_SECONDS,
    is_stt: bool = False,  # True para STT - usa rate limiter
) -> httpx.Response:
    """Realiza una petición POST con reintentos, backoff exponencial y circuit breaker."""
    
    # Rate limiting para STT
    if is_stt:
        acquired = await _stt_rate_limiter.acquire()
        if not acquired:
            # Esperar hasta que el circuit breaker se cierre
            for _ in range(30):  # Max 30s espera
                await asyncio.sleep(1)
                acquired = await _stt_rate_limiter.acquire()
                if acquired:
                    break
            if not acquired:
                raise RuntimeError("STT rate limit: Circuit breaker still open after 30s")
    
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if json_data is not None:
                    resp = await client.post(url, headers=headers, json=json_data)
                elif files is not None:
                    resp = await client.post(url, headers=headers, data=data, files=files)
                else:
                    resp = await client.post(url, headers=headers, data=data)
                
                # Manejo específico de Rate Limit (429)
                if resp.status_code == 429:
                    # Registrar error en circuit breaker
                    if is_stt:
                        _stt_rate_limiter.record_error(429)
                    
                    retry_after = resp.headers.get("retry-after")
                    try:
                        wait_time = float(retry_after) if retry_after else (INITIAL_RETRY_DELAY * (2**attempt))
                    except ValueError:
                        wait_time = INITIAL_RETRY_DELAY * (2**attempt)
                    
                    logger.warning(f"Rate limit hit (429) at {url}. Waiting {wait_time}s (attempt {attempt+1}/{MAX_RETRIES})")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        resp.raise_for_status()

                # Otros errores reintentables (5xx)
                if resp.status_code >= 500:
                    logger.warning(f"Server error {resp.status_code} at {url} (attempt {attempt+1}/{MAX_RETRIES})")
                    resp.raise_for_status()
                
                return resp
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            last_exc = e
            if attempt < MAX_RETRIES - 1:
                if not (isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429):
                    sleep_time = INITIAL_RETRY_DELAY * (2**attempt)
                    logger.info(f"Retrying in {sleep_time}s due to {type(e).__name__}...")
                    await asyncio.sleep(sleep_time)
            else:
                logger.error(f"Final attempt failed for {url}: {e}")
    
    if last_exc:
        raise last_exc
    raise RuntimeError(f"Failed to complete request to {url}")


async def text_to_speech_elevenlabs(
    text: str,
    *,
    voice: Optional[str] = None,
    stability: Optional[float] = None,
    similarity_boost: Optional[float] = None,
) -> str:
    """Text-to-Speech usando ElevenLabs (mejor para español)."""
    
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is not set")
    
    final_voice = (voice or ELEVENLABS_VOICE or "Antoni").strip()
    final_stability = stability if stability is not None else ELEVENLABS_STABILITY
    final_similarity = similarity_boost if similarity_boost is not None else ELEVENLABS_SIMILARITY_BOOST
    
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{final_voice}"
    
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY,
    }
    
    payload = {
        "text": text,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": {
            "stability": final_stability,
            "similarity_boost": final_similarity,
        }
    }
    
    try:
        resp = await _post_with_retry(url, headers=headers, json_data=payload)
        resp.raise_for_status()
        audio_bytes = resp.content
    except Exception as e:
        logger.error(f"ElevenLabs TTS failed after retries: {e}")
        raise
    
    b64 = base64.b64encode(audio_bytes).decode("ascii")
    return f"data:audio/mpeg;base64,{b64}"


def _get_groq_api_key() -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set")
    return api_key


def _get_groq_base_url() -> str:
    return os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").strip().rstrip("/")


def _get_groq_stt_model() -> str:
    # Usamos whisper-large-v3 para mejor precisión con múltiples voces y ruido
    return os.getenv("GROQ_STT_MODEL", "whisper-large-v3").strip()


def _get_groq_tts_model() -> str:
    return os.getenv("GROQ_TTS_MODEL", "grok-tts").strip()


def _get_groq_tts_voices() -> List[str]:
    raw = os.getenv("GROQ_TTS_VOICES", "").strip()
    if not raw:
        return []
    return [v.strip() for v in raw.split(",") if v.strip()]


def _get_default_voice() -> str:
    return os.getenv("GROQ_TTS_DEFAULT_VOICE", "default").strip() or "default"


def _get_tts_format() -> str:
    # Groq TTS solo acepta 'wav' según error 400
    fmt = os.getenv("GROQ_TTS_RESPONSE_FORMAT", "wav").strip().lower()
    if fmt not in {"wav"}:  # Solo wav es soportado por ahora
        return "wav"
    return fmt


def _mime_for_audio_format(fmt: str) -> str:
    if fmt == "wav":
        return "audio/wav"
    if fmt == "opus":
        # Commonly carried as Ogg Opus
        return "audio/ogg"
    return "audio/mpeg"


def _pcm16_to_wav_bytes(pcm16: bytes, *, sample_rate: int) -> bytes:
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16)
    return bio.getvalue()


def _infer_upload_meta(
    *,
    audio_format: str,
    sample_rate: int,
) -> Tuple[str, str, Callable[..., bytes]]:
    fmt = (audio_format or "").strip().lower()
    if fmt in {"pcm16", "pcm_s16le"}:
        wav_bytes = _pcm16_to_wav_bytes
        return ("audio.wav", "audio/wav", wav_bytes)
    if fmt in {"ogg", "ogg_opus", "opus", "audio/ogg"}:
        return ("audio.ogg", "audio/ogg", lambda b, **_: b)
    if fmt in {"webm", "webm_opus", "audio/webm"}:
        return ("audio.webm", "audio/webm", lambda b, **_: b)
    if fmt in {"mp3", "audio/mpeg"}:
        return ("audio.mp3", "audio/mpeg", lambda b, **_: b)
    if fmt in {"wav", "audio/wav"}:
        return ("audio.wav", "audio/wav", lambda b, **_: b)
    return ("audio.wav", "audio/wav", lambda b, **_: b)


def list_tts_voices() -> List[str]:
    voices = _get_groq_tts_voices()
    if voices:
        return voices
    # If not configured, we still return an empty list; frontend can allow free-form.
    return []


def normalize_voice(requested: Optional[str]) -> str:
    requested = (requested or "").strip()
    default_voice = _get_default_voice()

    if not requested:
        return default_voice

    allowed = _get_groq_tts_voices()
    if allowed and requested not in allowed:
        return default_voice

    return requested


async def transcribe_audio_groq(
    audio_bytes: bytes,
    *,
    language: Optional[str] = None,
    audio_format: str = "",
    sample_rate: int = 16000,
) -> str:
    """Speech-to-Text using Groq (OpenAI-compatible endpoint)."""

    api_key = _get_groq_api_key()
    base_url = _get_groq_base_url()
    model = _get_groq_stt_model()

    headers = {"Authorization": f"Bearer {api_key}"}

    data = {"model": model}
    if language:
        data["language"] = language

    filename, content_type, transform = _infer_upload_meta(audio_format=audio_format, sample_rate=sample_rate)
    try:
        send_bytes = transform(audio_bytes, sample_rate=sample_rate)
    except TypeError:
        send_bytes = transform(audio_bytes)

    files = {"file": (filename, send_bytes, content_type)}

    try:
        resp = await _post_with_retry(
            f"{base_url}/audio/transcriptions", 
            headers=headers, 
            data=data, 
            files=files,
            is_stt=True  # Activa rate limiting para STT
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        logger.error(f"Groq STT failed after retries: {e}")
        raise

    text = payload.get("text")
    if not isinstance(text, str):
        return ""
    return text


async def text_to_speech_groq(
    text: str,
    *,
    voice: Optional[str] = None,
    speed: Optional[float] = None,
    language: Optional[str] = None,
) -> str:
    """Text-to-Speech usando Groq o ElevenLabs según idioma."""
    
    # Truncar texto si es muy largo (Groq TTS tiene límite ~4000 chars)
    max_text_len = 3800
    original_len = len(text)
    if original_len > max_text_len:
        text = text[:max_text_len] + "..."
        logger.warning(f"TTS text truncated: {original_len} -> {max_text_len} chars")
    
    # Si es español y tenemos ElevenLabs configurado, usarlo
    if _should_use_elevenlabs(text, language):
        try:
            logger.info(f"Attempting TTS with ElevenLabs for text: {text[:50]}...")
            return await text_to_speech_elevenlabs(text, voice=voice)
        except Exception as e:
            logger.error(f"ElevenLabs TTS failed, falling back to Groq: {e}")
            # Fallback a Groq continúa abajo
    
    # Usar Groq TTS (principalmente para inglés o fallback)
    api_key = _get_groq_api_key()
    base_url = _get_groq_base_url()
    model = _get_groq_tts_model()

    fmt = _get_tts_format()
    mime = _mime_for_audio_format(fmt)
    final_voice = normalize_voice(voice)
    
    # Voces válidas de Groq (según el error 400 recibido)
    valid_groq_voices = ["autumn", "diana", "hannah", "austin", "daniel", "troy"]
    if final_voice not in valid_groq_voices:
        # Mapear voces comunes a voces soportadas por Groq
        voice_map = {
            "male_1": "austin",
            "male_2": "daniel",
            "female_1": "hannah",
            "female_2": "autumn",
            "default": "hannah"
        }
        final_voice = voice_map.get(final_voice, "hannah")
        logger.warning(f"Voice mapping: {final_voice} used instead of requested")

    payload = {
        "model": model,
        "voice": final_voice,
        "input": text,
    }
    # Groq TTS no usa 'format' ni 'speed' en todos los modelos
    if speed is not None and model not in ["grok-tts"]:
        payload["speed"] = speed
    if fmt and fmt != "mp3":
        payload["response_format"] = fmt

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    logger.info(f"TTS request: model={model}, voice={final_voice}, text_len={len(text)}")

    try:
        resp = await _post_with_retry(f"{base_url}/audio/speech", headers=headers, json_data=payload)
        if resp.status_code >= 400:
            error_body = resp.text[:500]
            logger.error(f"TTS error {resp.status_code}: {error_body}")
            logger.error(f"Payload was: model={model}, voice={final_voice}, text_preview={text[:100]}...")
            resp.raise_for_status()
        audio_bytes = resp.content
    except Exception as e:
        logger.error(f"Groq TTS failed after retries: {e}")
        raise

    b64 = base64.b64encode(audio_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"
