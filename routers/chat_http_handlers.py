"""
Chat HTTP Handlers - HTTP endpoints for chat API
Separado de unified_chat_router.py para reducir responsabilidades
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import UploadFile, File, Depends, HTTPException, APIRouter

from routers.chat_schemas import ChatResponse, STTResponse, TTSResponse, VoiceChatResponse, ChatMessageRequest
from routers.chat_context import get_user_context_for_chat, build_context_prompt
from routers.chat_progress import save_user_progress, _sanitize_structured_data
from routers.chat_search import perform_web_search, _should_web_search, prioritize_sources_with_images, _should_use_semantic_cache, _normalize_message_text
from routers.chat_ai import get_ai_response_http
from routers.chat_ws_utils import _estimate_duration_ms_from_bytes, _sanitize_sources_images, _build_rich_response
from services.groq_voice_service import transcribe_audio_groq, text_to_speech_groq
from services.groq_ai_service import get_context_info
from services.hub_memory_service import hub_memory_service
from utils.auth import get_current_user
from models.models import RecordingSession, RecordingSessionType, SessionItem

logger = logging.getLogger("chat_http_handlers")

router = APIRouter()
_WS_MAX_AUDIO_BYTES = 10 * 1024 * 1024


def _debug_enabled() -> bool:
    import os
    try:
        from config import DEBUG as CONFIG_DEBUG
        return bool(CONFIG_DEBUG)
    except Exception:
        return str(os.getenv("DEBUG") or "").strip() in {"1", "true", "True"}


def _new_request_id() -> str:
    import uuid
    return uuid.uuid4().hex[:12]


def _safe_meta(meta: Any) -> Dict[str, Any]:
    if not isinstance(meta, dict):
        return {}
    out: Dict[str, Any] = {}
    for k in ("status", "attempt", "key_index", "fallback", "attempts"):
        if k in meta:
            out[k] = meta.get(k)
    return out


async def handle_chat_message(
    message: str,
    files: Optional[List[UploadFile]],
    user: dict,
    stream: bool = False,
) -> ChatResponse:
    """Handle chat message HTTP endpoint"""
    user_id = user["user_id"]
    normalized_message = _normalize_message_text(message)
    request_id = _new_request_id()
    t0 = time.monotonic()
    
    should_web_search = _should_web_search(user_id=user_id, message=normalized_message)
    logger.info(
        f"chat_http_start request_id={request_id} user_id={user_id} "
        f"message_len={len(normalized_message or '')} web_search={should_web_search}"
    )
    
    # Check semantic cache
    from services.embeddings_service import embeddings_service
    cached_response = None
    if _should_use_semantic_cache(normalized_message):
        cached_response = await embeddings_service.get_cached_response(normalized_message)
    
    if cached_response and not stream:
        context_info = get_context_info(user_id)
        return ChatResponse(
            success=True,
            response=cached_response,
            user_id=user_id,
            timestamp=datetime.utcnow().isoformat(),
            context={
                "usage_percent": round(context_info.get("usage", 0) * 100, 1),
                "cache_hit": True
            },
            message_id=f"msg_cached_{datetime.utcnow().timestamp()}"
        )
    
    # Get user context
    user_context = await get_user_context_for_chat(user_id)
    
    # Web search
    sources: List[Dict[str, Any]] = []
    if should_web_search:
        search_sources, search_meta = await perform_web_search(
            user_id=user_id,
            query=normalized_message,
            include_images=_should_web_search(user_id=user_id, message=normalized_message)
        )
        sources = prioritize_sources_with_images(search_sources, max_sources=5)
        if search_sources:
            user_context = dict(user_context)
            user_context["web_search_results"] = list(search_sources)[:5]
    
    # Get AI response
    ai_text = await get_ai_response_http(user_id, normalized_message, user_context, fast_reasoning=True)
    structured = _sanitize_structured_data({"response": ai_text, "tasks": [], "plan": [], "actions": [], "is_stream": False})
    
    logger.info(
        f"chat_http_done request_id={request_id} user_id={user_id} "
        f"duration_ms={int((time.monotonic()-t0)*1000)} "
        f"response_len={len(structured.get('response') or '')}"
    )
    
    # Save progress
    asyncio.create_task(save_user_progress(user_id, normalized_message, structured))
    
    # Add to cache
    if not structured.get("is_stream"):
        await embeddings_service.add_to_semantic_cache(normalized_message, structured["response"])
    
    # Build response
    context_info = get_context_info(user_id)
    message_id = f"msg_{datetime.utcnow().timestamp()}"
    sources = await _sanitize_sources_images(list(sources or []))
    rich = _build_rich_response(text=str(structured.get("response") or ""), memory_id=message_id, sources=sources)
    
    return ChatResponse(
        success=True,
        response=structured["response"],
        user_id=user_id,
        timestamp=datetime.utcnow().isoformat(),
        context={
            "usage_percent": round(context_info.get("usage", 0) * 100, 1),
            "needs_refresh": False,
            "auto_refreshed": False,
            "tasks_count": len(user_context.get("tasks_today", [])),
            "upcoming_tasks_count": len(user_context.get("tasks_upcoming", []))
        },
        message_id=message_id,
        actions=[
            {"type": "tasks", "data": structured["tasks"]},
            {"type": "plan", "data": structured["plan"]}
        ],
        sources=sources if sources else None,
        rich_response=rich,
    )


async def handle_chat_message_json(
    request: ChatMessageRequest,
    user: dict,
) -> ChatResponse:
    """Handle chat message JSON endpoint"""
    return await handle_chat_message(
        message=request.message,
        files=None,
        user=user,
        stream=False
    )


async def handle_stt(
    audio: UploadFile,
    language: str,
    user: dict,
) -> STTResponse:
    """Handle speech-to-text endpoint"""
    audio_bytes = await audio.read()
    audio_format = audio.content_type or ""
    text = await transcribe_audio_groq(audio_bytes, language=language, audio_format=audio_format)
    return STTResponse(
        success=True,
        text=text,
        language=language or "es",
        duration_ms=_estimate_duration_ms_from_bytes(len(audio_bytes)),
        timestamp=datetime.utcnow().isoformat(),
    )


async def handle_tts(
    text: str,
    voice: Optional[str],
    speed: float,
    language: str,
    user: dict,
) -> TTSResponse:
    """Handle text-to-speech endpoint"""
    text = (text or "").strip()
    if not text or len(text) > 5000:
        raise HTTPException(status_code=400, detail="text_empty_or_too_long_max_5000")
    audio_uri = await text_to_speech_groq(text, voice=voice or "male_1", speed=speed, language=language)
    return TTSResponse(
        success=True,
        audio=audio_uri,
        text=text,
        voice=voice or "male_1",
        timestamp=datetime.utcnow().isoformat(),
    )


async def handle_voice_message(
    audio: UploadFile,
    language: str,
    voice: Optional[str],
    user: dict,
) -> VoiceChatResponse:
    """Handle voice chat endpoint: STT -> LLM -> TTS"""
    user_id = user["user_id"]
    audio_bytes = await audio.read()
    if len(audio_bytes) > _WS_MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="audio_too_large_max_10mb")

    audio_format = audio.content_type or ""
    transcribed = await transcribe_audio_groq(audio_bytes, language=language, audio_format=audio_format)

    user_context = await get_user_context_for_chat(user_id)
    response_text = await get_ai_response_http(user_id, transcribed, user_context, fast_reasoning=True)
    audio_uri = await text_to_speech_groq(response_text, voice=voice or "male_1", language=language)

    return VoiceChatResponse(
        success=True,
        transcribed=transcribed,
        response=response_text,
        audio=audio_uri,
        user_id=user_id,
        timestamp=datetime.utcnow().isoformat(),
        message_id=f"voice_{datetime.utcnow().timestamp()}",
    )
