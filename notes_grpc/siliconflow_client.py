from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from notes_grpc.groq_client import GroqClient


@dataclass
class TranscriptionResult:
    text: str


class LegacyGroqClient:
    def __init__(self) -> None:
        self._inner = GroqClient()

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def transcribe(self, *, audio_bytes: bytes, audio_mime: str, language: Optional[str] = None) -> TranscriptionResult:
        tr = await self._inner.transcribe(audio_bytes=audio_bytes, audio_mime=audio_mime, language=language)
        return TranscriptionResult(text=tr.text)

    async def chat_json(self, *, system: str, user: str) -> Dict[str, Any]:
        return await self._inner.chat_json(system=system, user=user)


__all__ = [
    "TranscriptionResult",
    "LegacyGroqClient",
]
