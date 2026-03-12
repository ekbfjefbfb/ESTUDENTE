from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from services.groq_ai_service import chat_with_ai, sanitize_ai_text
from services.groq_voice_service import transcribe_audio_groq


@dataclass
class TranscriptionResult:
    text: str


class GroqClient:
    async def aclose(self) -> None:
        return None

    async def transcribe(
        self,
        *,
        audio_bytes: bytes,
        audio_mime: str,
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        text = await transcribe_audio_groq(audio_bytes, language=language or "es")
        return TranscriptionResult(text=(text or "").strip())

    async def chat_json(self, *, system: str, user: str) -> Dict[str, Any]:
        content = await chat_with_ai(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=False,
        )

        if not isinstance(content, str):
            raise RuntimeError("LLM returned non-text content")

        # Sanitizar antes de parsear JSON
        content = sanitize_ai_text(content)

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"LLM did not return JSON. content={content!r}") from e
