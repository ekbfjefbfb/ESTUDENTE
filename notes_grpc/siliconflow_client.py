from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from notes_grpc.config import settings


@dataclass
class TranscriptionResult:
    text: str


class SiliconFlowClient:
    def __init__(self) -> None:
        if not settings.SILICONFLOW_API_KEY:
            raise RuntimeError("SILICONFLOW_API_KEY is not set")

        self._base_url = settings.SILICONFLOW_BASE_URL.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {settings.SILICONFLOW_API_KEY}",
        }
        self._client = httpx.AsyncClient(timeout=60.0, headers=self._headers)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def transcribe(self, *, audio_bytes: bytes, audio_mime: str, language: Optional[str] = None) -> TranscriptionResult:
        url = f"{self._base_url}/audio/transcriptions"

        files = {
            "file": ("audio", audio_bytes, audio_mime or "application/octet-stream"),
        }
        data: Dict[str, Any] = {
            "model": settings.STT_MODEL,
        }
        if language:
            data["language"] = language

        resp = await self._client.post(url, data=data, files=files)
        resp.raise_for_status()
        payload = resp.json()

        text = payload.get("text")
        if not isinstance(text, str):
            raise RuntimeError(f"Unexpected transcription response: {payload}")
        return TranscriptionResult(text=text)

    async def chat_json(self, *, system: str, user: str) -> Dict[str, Any]:
        """Calls /chat/completions and expects a JSON object in the assistant content."""
        url = f"{self._base_url}/chat/completions"

        body: Dict[str, Any] = {
            "model": settings.LLM_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_tokens": 1200,
            "response_format": {"type": "json_object"},
        }

        resp = await self._client.post(url, json=body)
        resp.raise_for_status()
        payload = resp.json()

        try:
            content = payload["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"Unexpected chat response structure: {payload}") from e

        if not isinstance(content, str):
            raise RuntimeError(f"Unexpected chat content: {content}")

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"LLM did not return JSON. content={content!r}") from e
