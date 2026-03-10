from __future__ import annotations

from typing import Any, Dict

from services.groq_ai_service import (
    chat_with_ai,
    get_context_info,
    should_refresh_context,
    user_contexts,
)


async def transcribe_audio(audio_bytes: bytes) -> str:
    from services.groq_voice_service import transcribe_audio_groq

    text = await transcribe_audio_groq(audio_bytes, language="es")
    return (text or "").strip()


async def text_to_speech(text: str) -> str:
    from services.groq_voice_service import normalize_voice, text_to_speech_groq

    audio_data = await text_to_speech_groq(text, voice=normalize_voice(None), speed=1.0)
    return audio_data


__all__ = [
    "chat_with_ai",
    "should_refresh_context",
    "get_context_info",
    "user_contexts",
    "transcribe_audio",
    "text_to_speech",
]
