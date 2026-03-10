from __future__ import annotations

import base64
import io
import os
import wave
from typing import Callable, List, Optional, Tuple

import httpx


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

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{base_url}/audio/transcriptions", headers=headers, data=data, files=files)
        resp.raise_for_status()
        payload = resp.json()

    text = payload.get("text")
    if not isinstance(text, str):
        return ""
    return text


async def text_to_speech_groq(
    text: str,
    *,
    voice: Optional[str] = None,
    speed: Optional[float] = None,
) -> str:
    """Text-to-Speech using Groq (OpenAI-compatible endpoint). Returns a base64 data URI."""

    api_key = _get_groq_api_key()
    base_url = _get_groq_base_url()
    model = _get_groq_tts_model()

    fmt = _get_tts_format()
    mime = _mime_for_audio_format(fmt)
    final_voice = normalize_voice(voice)

    payload = {
        "model": model,
        "voice": final_voice,
        "input": text,
        "format": fmt,
    }
    if speed is not None:
        payload["speed"] = speed

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{base_url}/audio/speech", headers=headers, json=payload)
        resp.raise_for_status()
        audio_bytes = resp.content

    b64 = base64.b64encode(audio_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"
