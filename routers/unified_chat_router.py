"""
Unified Chat Router v6.0 - Refactored
Router orquestador que delega a módulos especializados
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from sqlalchemy.orm import Session
from database import get_db

# Schemas
from routers.chat_schemas import (
    ChatResponse, ChatMessageRequest,
    STTResponse, TTSResponse, VoiceChatResponse,
)

# Context
from routers.chat_context import get_user_context_for_chat, invalidate_user_context

# Progress
from routers.chat_progress import (
    get_user_progress, complete_task, save_user_plan
)

# HTTP Handlers
from routers.chat_http_handlers import (
    handle_chat_message, handle_chat_message_json,
    handle_stt, handle_tts, handle_voice_message
)

# WebSocket Handlers
from routers.chat_ws_handlers import handle_chat_websocket

# Utils
from routers.chat_search import _normalize_message_text
from utils.auth import get_current_user
from services.chat_session_service import chat_session_service
from services.voice_ws_session import VoiceWsConfig, VoiceWsSession
from services.groq_ai_service import chat_with_ai
from utils.rate_limit import RateLimitRule, evaluate_rate_limits
from routers.chat_ws_utils import (
    _ws_auth_user_id, _ws_send_json, _ws_heartbeat,
    _estimate_duration_ms_from_bytes, _tail_bytes_for_pcm16
)
from utils.file_processing import SUPPORTED_IMAGE_TYPES, SUPPORTED_DOCUMENT_TYPES, MAX_FILE_SIZE_BYTES
from config import (
    BACKEND_PUBLIC_URL,
    CHAT_VOICE_WS_PUBLIC_URL,
    DEEPGRAM_AGENT_OPENAI_PUBLIC_URL,
    DEEPGRAM_AGENT_PUBLIC_URL,
    GOOGLE_OAUTH_AUTHORIZE_PATH,
    GOOGLE_OAUTH_CALLBACK_PATH,
    GOOGLE_OAUTH_EXCHANGE_PATH,
    GOOGLE_REDIRECT_URI,
    OAUTH_ENABLED,
)

logger = logging.getLogger("unified_chat_router")
router = APIRouter(tags=["Chat IA"])
_VOICE_WS_CONNECT_RULES = (
    RateLimitRule(name="voice_ws_connect_ip", scope="ip", max_requests=20, window_seconds=60, block_seconds=120),
    RateLimitRule(name="voice_ws_connect_user", scope="user", max_requests=8, window_seconds=60, block_seconds=120),
)


def _request_public_base_url(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}".rstrip("/")
    if BACKEND_PUBLIC_URL:
        return BACKEND_PUBLIC_URL.rstrip("/")
    return str(request.base_url).rstrip("/")


def _ws_url_from_http_base(base_url: str, path: str) -> str:
    normalized_base = str(base_url or "").rstrip("/")
    if normalized_base.startswith("https://"):
        return f"wss://{normalized_base[len('https://'):]}{path}"
    if normalized_base.startswith("http://"):
        return f"ws://{normalized_base[len('http://'):]}{path}"
    return f"{normalized_base}{path}"


def _build_client_config(request: Request) -> Dict[str, Any]:
    base_url = _request_public_base_url(request)
    try:
        from services.google_workspace.google_auth_service import google_auth_service

        google_config = google_auth_service.get_public_config()
    except Exception:
        google_config = {
            "enabled": bool(OAUTH_ENABLED),
            "redirect_uri": GOOGLE_REDIRECT_URI,
        }

    return {
        "service": "unified-chat",
        "version": "6.0",
        "model": "auto",
        "provider": "Groq",
        "features": {
            "text_chat": True,
            "voice_chat": True,
            "websocket": True,
            "context_monitoring": True,
            "auto_context_refresh": True,
            "multipart_chat": True,
            "websocket_attachments": False,
            "json_attachments": False,
            "google_oauth": bool(google_config.get("enabled")),
            "deepgram_agent_proxy": True,
        },
        "limits": {
            "max_context_tokens": 32000,
            "context_threshold_percent": 85,
            "max_audio_size_mb": 10,
            "max_file_size_mb": round(MAX_FILE_SIZE_BYTES / (1024 * 1024), 2),
        },
        "multipart": {
            "required_for_attachments": True,
            "fields": {
                "message": "text",
                "files": "list[file]",
                "images": "list[file]",
                "documents": "list[file]",
                "force_web_search": "bool",
                "session_id": "string",
            },
            "supported_image_types": sorted(SUPPORTED_IMAGE_TYPES),
            "supported_document_types": sorted(SUPPORTED_DOCUMENT_TYPES),
        },
        "frontend": {
            "message_url": f"{base_url}/api/unified-chat/message",
            "message_json_url": f"{base_url}/api/unified-chat/message/json",
            "history_url_template": f"{base_url}/api/unified-chat/sessions/{{session_id}}/history",
            "ws_url_template": f"{_ws_url_from_http_base(base_url, '/api/unified-chat/ws/{user_id}')}?token={{jwt}}",
            "voice_ws_url": CHAT_VOICE_WS_PUBLIC_URL or _ws_url_from_http_base(base_url, "/api/unified-chat/voice/ws"),
            "attachments_transport": "multipart/form-data",
        },
        "voice_agent": {
            "provider": "deepgram-custom-llm",
            "chat_url": DEEPGRAM_AGENT_PUBLIC_URL or f"{base_url}/api/deepgram/chat",
            "openai_compatible_url": DEEPGRAM_AGENT_OPENAI_PUBLIC_URL or f"{base_url}/api/deepgram/v1/chat/completions",
            "auth": {
                "type": "bearer",
                "header": "Authorization",
                "format": "Bearer <access_token>",
            },
        },
        "oauth": {
            "google": {
                "enabled": bool(google_config.get("enabled")),
                "authorize_url": f"{base_url}{GOOGLE_OAUTH_AUTHORIZE_PATH}",
                "exchange_code_url": f"{base_url}{GOOGLE_OAUTH_EXCHANGE_PATH}",
                "callback_url": f"{base_url}{GOOGLE_OAUTH_CALLBACK_PATH}",
                "redirect_uri": google_config.get("redirect_uri") or GOOGLE_REDIRECT_URI,
            }
        },
    }


# ============== HTTP ENDPOINTS ==============

@router.get("/info")
async def chat_info(request: Request):
    """Información del servidor de chat para frontend"""
    return _build_client_config(request)


@router.get("/client-config")
async def chat_client_config(request: Request):
    """Configuración explícita para frontend móvil/web."""
    return _build_client_config(request)


@router.get("/health")
async def chat_health():
    """Health liviano del subsistema de chat para frontend y monitoreo."""
    return {
        "service": "unified-chat",
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ============== CHAT SESSION MANAGEMENT ==============

@router.get("/sessions")
async def list_chat_sessions(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Listar todos los hilos de chat del usuario"""
    user_id = user["user_id"]
    sessions = chat_session_service.get_user_sessions(db, user_id)
    return {
        "success": True,
        "sessions": [
            {
                "id": s.id,
                "title": s.title,
                "topic": s.topic,
                "updated_at": s.updated_at.isoformat(),
                "created_at": s.created_at.isoformat()
            } for s in sessions
        ]
    }


@router.post("/sessions")
async def create_chat_session(
    title: Optional[str] = Query("Nueva Conversación"),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Crear un nuevo hilo de chat académico"""
    user_id = user["user_id"]
    session = chat_session_service.create_session(db, user_id, title)
    return {
        "success": True,
        "session_id": session.id,
        "title": session.title
    }


@router.get("/sessions/{session_id}/history")
async def get_chat_session_history(
    session_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Obtener el historial COMPLETO de un hilo específico para el frontend"""
    user_id = user["user_id"]
    history = chat_session_service.get_session_history(
        db,
        session_id=session_id,
        user_id=user_id,
    )
    if not history and chat_session_service.get_session(db, session_id=session_id, user_id=user_id) is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    
    return {
        "success": True,
        "session_id": session_id,
        "history": [
            {
                "role": m.role,
                "content": m.content,
                "media": m.media_metadata,
                "timestamp": m.created_at.isoformat()
            } for m in history
        ]
    }


@router.delete("/sessions/{session_id}")
async def delete_chat_session(
    session_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Borrar/Archivar un hilo de chat"""
    deleted = chat_session_service.delete_session(db, session_id, user["user_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="session_not_found")
    return {"success": True, "message": "Sesión eliminada"}


@router.post("/message", response_model=ChatResponse)
async def unified_chat_message(
    message: str = Form(""),
    files: Optional[List[UploadFile]] = File(None),
    images: Optional[List[UploadFile]] = File(None),
    documents: Optional[List[UploadFile]] = File(None),
    user: dict = Depends(get_current_user),
    stream: bool = Query(False),
    force_web_search: bool = Form(False),
    session_id: Optional[str] = Form(None),
):
    """Chat con IA - multipart/form-data (campo de texto `message` + imágenes/documentos)."""
    return await handle_chat_message(
        message=_normalize_message_text(message),
        files=files,
        images=images,
        documents=documents,
        user=user,
        stream=stream,
        force_web_search=force_web_search,
        session_id=session_id
    )


@router.post("/message/json", response_model=ChatResponse)
async def unified_chat_message_json(
    request: ChatMessageRequest,
    user: dict = Depends(get_current_user),
):
    """Chat con IA - JSON body solo texto. Adjuntos: usar /message multipart."""
    return await handle_chat_message_json(request=request, user=user)


@router.post("/stt", response_model=STTResponse)
async def stt_endpoint(
    audio: UploadFile = File(...),
    language: str = "es",
    user: dict = Depends(get_current_user),
):
    """Speech-to-Text"""
    return await handle_stt(audio=audio, language=language, user=user)


@router.post("/tts", response_model=TTSResponse)
async def tts_endpoint(
    text: str,
    voice: Optional[str] = "male_1",
    speed: float = 1.0,
    language: str = "es",
    user: dict = Depends(get_current_user),
):
    """Text-to-Speech"""
    return await handle_tts(
        text=text, voice=voice, speed=speed, language=language, user=user
    )


@router.post("/voice/message", response_model=VoiceChatResponse)
async def voice_message_http(
    audio: UploadFile = File(...),
    language: str = "es",
    voice: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Chat por voz via HTTP: STT -> LLM -> TTS"""
    return await handle_voice_message(
        audio=audio, language=language, voice=voice, user=user
    )


# ============== PROGRESS ENDPOINTS ==============

@router.get("/progress")
async def get_user_progress_endpoint(user=Depends(get_current_user)):
    """Obtener progreso del usuario"""
    user_id = user["user_id"]
    progress = get_user_progress(user_id)
    return {
        "success": True,
        **progress
    }


@router.post("/progress/complete/{task_id}")
async def complete_task_endpoint(task_id: str, user=Depends(get_current_user)):
    """Marcar tarea como completada"""
    user_id = user["user_id"]
    completed = complete_task(user_id, task_id)
    return {
        "success": completed,
        "message": "Tarea completada" if completed else "Tarea no encontrada"
    }


@router.post("/progress/plan")
async def save_plan_endpoint(
    plan: List[dict],
    user=Depends(get_current_user)
):
    """Guardar plan de estudio"""
    user_id = user["user_id"]
    save_user_plan(user_id, plan)
    return {"success": True, "message": "Plan guardado"}


@router.get("/progress/stats")
async def get_progress_stats(user=Depends(get_current_user)):
    """Obtener estadísticas de progreso"""
    user_id = user["user_id"]
    user_context = await get_user_context_for_chat(user_id)
    
    total_today = len(user_context.get("tasks_today", []))
    completed_today = 0
    
    return {
        "success": True,
        "stats": {
            "tasks_today": total_today,
            "tasks_completed_today": completed_today,
            "tasks_upcoming": len(user_context.get("tasks_upcoming", [])),
            "completion_rate": round(completed_today / max(total_today, 1) * 100, 1)
        }
    }


@router.post("/context/refresh/{user_id}")
async def refresh_user_context(user_id: str, user: dict = Depends(get_current_user)):
    """Forzar refresh del contexto del usuario"""
    token_user_id = str(user.get("user_id") or user.get("id") or "")
    if token_user_id != str(user_id):
        raise HTTPException(status_code=403, detail="forbidden_user_id_mismatch")
    invalidate_user_context(user_id)
    return {
        "success": True,
        "user_id": user_id,
        "timestamp": datetime.utcnow().isoformat()
    }


# ============== WEBSOCKET ENDPOINTS ==============

@router.websocket("/ws/{user_id}")
async def unified_chat_websocket(websocket: WebSocket, user_id: str):
    """WebSocket para chat en tiempo real"""
    await handle_chat_websocket(websocket, user_id)


@router.websocket("/voice/ws")
async def voice_stream_ws(websocket: WebSocket):
    """WebSocket para voz en streaming: STT parcial -> LLM -> TTS"""
    await websocket.accept()
    logger.info("Voice WebSocket connection accepted")

    try:
        user_id = await _ws_auth_user_id(websocket)
        logger.info(f"Voice WebSocket authenticated: user_id={user_id}")
    except Exception as e:
        logger.warning(f"Voice WebSocket auth failed: {e}")
        await _ws_send_json(websocket, {"type": "error", "message": "auth_failed"})
        await websocket.close(code=1008)
        return

    decisions = await evaluate_rate_limits(
        namespace="voice_ws_connect",
        identifiers={
            "ip": websocket.client.host if websocket.client and websocket.client.host else "unknown",
            "user": str(user_id),
        },
        rules=_VOICE_WS_CONNECT_RULES,
    )
    blocked = next((decision for decision in decisions if not decision.allowed), None)
    if blocked is not None:
        await _ws_send_json(
            websocket,
            {
                "type": "error",
                "message": "rate_limited",
                "scope": blocked.scope,
                "retry_after_seconds": blocked.retry_after,
            },
        )
        await websocket.close(code=1013)
        return

    session = VoiceWsSession(
        send_json=lambda payload: _ws_send_json(websocket, payload),
        chat_with_ai=chat_with_ai,
        now_ts=lambda: datetime.utcnow().isoformat(),
        estimate_duration_ms=_estimate_duration_ms_from_bytes,
        tail_bytes_for_pcm16=_tail_bytes_for_pcm16,
        config=VoiceWsConfig(
            max_audio_bytes=10 * 1024 * 1024,
            partial_interval_ms=400,
            tail_window_ms=4500,
        ),
    )

    heartbeat_task = None
    try:
        heartbeat_task = asyncio.create_task(_ws_heartbeat(websocket, str(user_id)))
        while True:
            try:
                msg = await websocket.receive()
            except WebSocketDisconnect:
                break
            except Exception:
                break

            if msg.get("type") == "websocket.disconnect":
                break

            if "text" in msg and msg["text"] is not None:
                try:
                    data = json.loads(msg["text"])
                    mtype = data.get("type")
                except Exception:
                    continue

                if mtype == "start":
                    await session.start_turn(data, user_id=user_id)
                elif mtype == "end":
                    await session.end_turn(user_id=user_id)

            if "bytes" in msg and msg["bytes"] is not None:
                chunk = msg["bytes"]
                if not isinstance(chunk, (bytes, bytearray)):
                    continue
                if not session.started:
                    await session.start_turn({
                        "format": "pcm16", "sample_rate": 16000,
                        "language": "es", "mode": "voice_chat", "vad": True
                    }, user_id=user_id)
                try:
                    await session.add_audio_chunk(bytes(chunk))
                except ValueError:
                    await websocket.close(code=1009)
                    return
    except Exception as e:
        logger.exception(f"Voice WebSocket error: {e}")
    finally:
        if heartbeat_task is not None:
            heartbeat_task.cancel()


__all__ = ["router"]
