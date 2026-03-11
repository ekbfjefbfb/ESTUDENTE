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
    """Decide si usar ElevenLabs (español) o Groq TTS (inglés)."""
    if not USE_ELEVENLABS_API or not ELEVENLABS_API_KEY:
        return False
    # Si el idioma es español o no especificado pero el texto parece español
    if language and language.lower() in ("es", "spa", "spanish"):
        return True
    # Detección simple: presencia de caracteres típicos del español
    spanish_markers = ["ñ", "á", "é", "í", "ó", "ú", "ü", "¿", "¡"]
    text_lower = text.lower()
    if any(marker in text_lower for marker in spanish_markers):
        return True
    return False


async def _post_with_retry(
    url: str,
    headers: Dict[str, str],
    json_data: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    timeout: float = TIMEOUT_SECONDS,
) -> httpx.Response:
    """Realiza una petición POST con reintentos y backoff exponencial."""
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
                
                # Si es 429 (Rate Limit) o 5xx (Server Error), reintentar
                if resp.status_code == 429 or resp.status_code >= 500:
                    logger.warning(f"Retryable error {resp.status_code} at {url} (attempt {attempt+1}/{MAX_RETRIES})")
                    resp.raise_for_status()
                
                return resp
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            last_exc = e
            if attempt < MAX_RETRIES - 1:
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
    return os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo").strip()


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
    fmt = os.getenv("GROQ_TTS_RESPONSE_FORMAT", "mp3").strip().lower()
    if fmt not in {"mp3", "wav", "opus"}:
        return "mp3"
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
        resp = await _post_with_retry(f"{base_url}/audio/transcriptions", headers=headers, data=data, files=files)
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
            return await text_to_speech_elevenlabs(text, voice=voice)
        except Exception:
            # Fallback a Groq si ElevenLabs falla
            pass
    
    # Usar Groq TTS (principalmente para inglés)
    api_key = _get_groq_api_key()
    base_url = _get_groq_base_url()
    model = _get_groq_tts_model()

    fmt = _get_tts_format()
    mime = _mime_for_audio_format(fmt)
    final_voice = normalize_voice(voice)
    
    # Voces válidas de Groq (según el error 400 recibido)
    valid_groq_voices = ["autumn", "diana", "hannah", "austin", "daniel", "troy"]
    if final_voice not in valid_groq_voices:
        logger.warning(f"Invalid Groq TTS voice '{final_voice}', using 'hannah' (default)")
        final_voice = "hannah"

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
