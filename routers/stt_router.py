from __future__ import annotations

import os
from typing import Optional

import anyio
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field

from utils.auth import get_current_user


router = APIRouter(prefix="/api/stt", tags=["STT"])


class TranscriptionOut(BaseModel):
    text: str
    language: Optional[str] = None
    duration: Optional[float] = None
    provider: str = Field(default="groq")
    model: str = Field(default="whisper-large-v3-turbo")


@router.post("/groq/transcribe", response_model=TranscriptionOut)
async def groq_transcribe_audio(
    file: UploadFile,
    _user=Depends(get_current_user),
):
    api_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="missing_groq_api_key")

    if not file:
        raise HTTPException(status_code=400, detail="missing_audio_file")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty_audio_file")

    filename = file.filename or "audio"

    def _do_transcribe():
        from groq import Groq

        client = Groq(api_key=api_key)
        transcription = client.audio.transcriptions.create(
            file=(filename, raw),
            model="whisper-large-v3-turbo",
            temperature=0,
            response_format="verbose_json",
        )
        text = getattr(transcription, "text", None) or ""
        language = getattr(transcription, "language", None)
        duration = getattr(transcription, "duration", None)
        return text, language, duration

    try:
        text, language, duration = await anyio.to_thread.run_sync(_do_transcribe)
    except Exception:
        raise HTTPException(status_code=502, detail="groq_transcription_failed")

    return TranscriptionOut(text=str(text or "").strip(), language=language, duration=duration)
