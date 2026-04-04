"""
Chat HTTP Handlers - HTTP endpoints for chat API
Separado de unified_chat_router.py para reducir responsabilidades
"""
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import UploadFile, HTTPException, APIRouter

from routers.chat_schemas import ChatResponse, STTResponse, TTSResponse, VoiceChatResponse, ChatMessageRequest
from routers.chat_context import get_user_context_for_chat
from routers.chat_progress import save_user_progress, _sanitize_structured_data
from routers.chat_search import (
    perform_web_search,
    _should_web_search,
    _should_include_images_in_search,
    prioritize_sources_with_images,
    _should_use_semantic_cache,
    _normalize_message_text,
)
from routers.chat_ai import get_ai_response_http
from routers.chat_ws_utils import _estimate_duration_ms_from_bytes, _sanitize_sources_images, _build_rich_response
from services.groq_voice_service import transcribe_audio_groq, text_to_speech_groq
from services.groq_ai_service import get_context_info
from services.orchestration_service import scout
from services.agent_service import agent_manager
from utils.file_processing import process_uploaded_files
from models.models import ChatSession

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
    files: Optional[List[UploadFile]] = None,
    images: Optional[List[UploadFile]] = None,
    documents: Optional[List[UploadFile]] = None,
    user: dict = None,
    stream: bool = False,
    force_web_search: bool = False,
    pre_processed_file_content: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
) -> ChatResponse:
    """Handle chat message HTTP endpoint"""
    user_id = user["user_id"]
    normalized_message = _normalize_message_text(message)
    request_id = _new_request_id()
    t0 = time.monotonic()
    
    # Combine all file sources for processing
    all_files = []
    if files:
        all_files.extend(files)
    if images:
        all_files.extend(images)
    if documents:
        all_files.extend(documents)

    # Process uploaded files (images and documents)
    file_content = pre_processed_file_content
    if all_files:
        try:
            image_contents, text_contents = await process_uploaded_files(all_files)
            if image_contents or text_contents:
                file_content = {
                    "images": image_contents,
                    "texts": text_contents
                }
                logger.info(f"Processed {len(image_contents)} images and {len(text_contents)} documents for user {user_id}")
        except Exception as e:
            logger.error(f"Error processing files: {e}")
            # Continue without files if processing fails
    
    should_web_search = _should_web_search(
        user_id=user_id, message=normalized_message, force=force_web_search
    )
    logger.info(
        f"chat_http_start request_id={request_id} user_id={user_id} "
        f"message_len={len(normalized_message or '')} web_search={should_web_search} has_files={bool(file_content)}"
    )
    
    # Check semantic cache (skip cache if has files)
    from services.embeddings_service import embeddings_service
    cached_response = None
    if _should_use_semantic_cache(normalized_message) and not file_content:
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
    
    # Web search (skip if has files to prioritize file analysis)
    sources: List[Dict[str, Any]] = []
    if should_web_search and not file_content:
        search_sources, search_meta = await perform_web_search(
            user_id=user_id,
            query=normalized_message,
            include_images=_should_include_images_in_search(normalized_message),
        )
        sources = prioritize_sources_with_images(search_sources, max_sources=5)
        if search_sources:
            user_context = dict(user_context)
            user_context["web_search_results"] = list(search_sources)[:5]
    
    # Get AI response (with file content and robust HISTORY)
    chat_history = user_context.get("chat_history", [])
    
    # PERSISTENCE: Save user message and handle session logic
    from database import SessionLocal
    from services.chat_session_service import chat_session_service
    db = SessionLocal()
    try:
        # Resolve session_id
        if session_id:
            session = chat_session_service.get_session(
                db,
                session_id=session_id,
                user_id=user_id,
            )
            if session is None:
                raise HTTPException(status_code=404, detail="session_not_found")
        else:
            # Try to get the most recent session or create a new one
            sessions = chat_session_service.get_user_sessions(db, user_id, limit=1)
            if sessions:
                session_id = sessions[0].id
            else:
                new_session = chat_session_service.create_session(db, user_id)
                session_id = new_session.id
        
        # Save user message to database
        chat_session_service.add_message(
            db=db,
            session_id=session_id,
            user_id=user_id,
            role="user",
            content=normalized_message,
            media_metadata=file_content,
            request_id=request_id
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error persisting user message: {e}")
    finally:
        db.close()
    
    # Scout Intelligent Decision
    if scout.should_use_agents(normalized_message, history=chat_history):
        # For HTTP, we can't stream tokens as easily, but we run the agent task
        ai_text = await agent_manager.run_complex_task(normalized_message, user_id=user_id, history=chat_history)
        if hasattr(ai_text, "summary"):
            ai_text = ai_text.summary
    else:
        ai_text = await get_ai_response_http(
            user_id, 
            normalized_message, 
            user_context, 
            fast_reasoning=True,
            file_content=file_content
        )
    structured = _sanitize_structured_data({"response": ai_text, "tasks": [], "plan": [], "actions": [], "is_stream": False})
    
    logger.info(
        f"chat_http_done request_id={request_id} user_id={user_id} "
        f"duration_ms={int((time.monotonic()-t0)*1000)} "
        f"response_len={len(structured.get('response') or '')}"
    )
    
    # PERSISTENCE: Save AI response and detect naming need
    db = SessionLocal()
    try:
        chat_session_service.add_message(
            db=db,
            session_id=session_id,
            user_id=user_id,
            role="assistant",
            content=structured.get("response") or "",
            request_id=request_id
        )
        
        # Simple Naming logic: rename if session title is default and we have history
        session_info = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        ).first()
        if session_info and session_info.title == "Nueva Conversación":
            from utils.background import safe_create_task
            safe_create_task(
                chat_session_service.auto_rename_session(session_id, normalized_message),
                name=f"rename_session_{session_id}"
            )
    except Exception as e:
        logger.error(f"Error persisting AI response: {e}")
    finally:
        db.close()
    
    # Save progress
    from utils.background import safe_create_task
    safe_create_task(save_user_progress(user_id, normalized_message, structured), name="save_user_progress")
    
    # Add to cache (only if no files)
    if not structured.get("is_stream") and not file_content:
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
    # Procesar archivos base64 del JSON si existen
    from utils.file_processing import process_base64_files
    
    image_contents, text_contents = await process_base64_files(
        images_base64=request.images,
        docs_base64=request.documents or request.files
    )
    
    pre_file_content = None
    if image_contents or text_contents:
        pre_file_content = {
            "images": image_contents,
            "texts": text_contents
        }

    return await handle_chat_message(
        message=request.message,
        files=None,
        images=None, 
        documents=None,
        user=user,
        stream=False,
        force_web_search=bool(getattr(request, "web_search", False)),
        pre_processed_file_content=pre_file_content,
        session_id=request.session_id
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
