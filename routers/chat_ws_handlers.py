"""
Chat WebSocket Handlers - WebSocket handlers for chat
Separado de unified_chat_router.py para reducir responsabilidades
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
import time

from fastapi import WebSocket, WebSocketDisconnect, HTTPException

from routers.chat_context import get_user_context_for_chat, invalidate_user_context
from routers.chat_search import perform_web_search, prioritize_sources_with_images
from routers.chat_ai import get_ai_response_with_streaming
from routers.chat_ws_utils import (
    _ws_auth_user_id, _ws_send_json, _ws_send_status, _ws_heartbeat,
    _track_ws_auth_failure, _get_ws_backoff_seconds, _clear_ws_auth_failures,
    _ws_replace_existing_enabled, get_user_ws_lock, set_active_ws,
    get_active_ws, remove_active_ws, _sanitize_sources_images, _build_rich_response
)
from services.hub_memory_service import hub_memory_service
from services.youtube_transcript_service import youtube_transcript_service
from services.browser_mcp_service import browser_mcp_service
from utils.rate_limit import RateLimitRule, evaluate_rate_limits
from config import DEBUG

logger = logging.getLogger("chat_ws_handlers")

_MAX_MESSAGE_CHARS = 8000
_MAX_RAW_PAYLOAD_CHARS = int(os.getenv("CHAT_WS_MAX_PAYLOAD_CHARS", str(256 * 1024)))
_WS_CONNECT_RULES = (
    RateLimitRule(name="chat_ws_connect_ip", scope="ip", max_requests=30, window_seconds=60, block_seconds=120),
    RateLimitRule(name="chat_ws_connect_user", scope="user", max_requests=10, window_seconds=60, block_seconds=120),
)


async def _persist_ws_session_turn(
    user_id: str,
    session_id: str,
    ai_text: str,
    request_id: str,
    user_message_for_naming: str
):
    """
    Helper Senior: Persistencia atómica de la respuesta AI y trigger de nombrado.
    Evita duplicidad entre modo Agente y modo Chat.
    """
    from database import SessionLocal
    from models.models import ChatSession
    from services.chat_session_service import chat_session_service
    from utils.background import safe_create_task

    db = SessionLocal()
    try:
        # 1. Guardar respuesta del asistente
        chat_session_service.add_message(
            db=db, session_id=session_id, user_id=user_id,
            role="assistant", content=ai_text,
            request_id=request_id
        )
        # 2. Invalidar contexto para que la próxima vez lea el historial nuevo
        invalidate_user_context(user_id)

        # 3. Naming Inteligente (si es necesario)
        session_info = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        ).first()
        
        if _should_auto_rename_session(session_info):
            safe_create_task(
                chat_session_service.auto_rename_session(session_id, user_message_for_naming),
                name=f"rename_session_{session_id}"
            )
    except Exception as e:
        logger.error(f"Failed to persist WS AI response for user {user_id}: {e}")
    finally:
        db.close()


def _should_auto_rename_session(session_info: Any) -> bool:
    return getattr(session_info, "title", None) == "Nueva Conversación"


def _normalize_session_id(value: Any) -> Optional[str]:
    normalized = str(value or "").strip()
    if normalized.lower() in {"", "none", "null", "undefined"}:
        return None
    return normalized


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "si", "on"}
    return bool(value)


def _has_ws_attachment_payload(message_data: Dict[str, Any]) -> bool:
    return bool(
        message_data.get("images")
        or message_data.get("documents")
        or message_data.get("files")
    )


def _dedupe_signature(message_data: Dict[str, Any]) -> str:
    signature_payload = {
        "type": str(message_data.get("type") or "").strip().lower(),
        "session_id": _normalize_session_id(message_data.get("session_id")) or "",
        "message": str(message_data.get("message") or "").strip(),
        "web_search": _coerce_bool(message_data.get("web_search")),
        "search_web": _coerce_bool(message_data.get("search_web")),
    }
    try:
        return json.dumps(signature_payload, sort_keys=True, ensure_ascii=True)
    except Exception:
        return str(signature_payload)


async def handle_chat_websocket(websocket: WebSocket, user_id: str):
    """Handle chat WebSocket connection"""
    heartbeat_task: Optional[asyncio.Task] = None
    conn_lock: Optional[asyncio.Lock] = None
    client_ip = websocket.client.host if websocket.client and websocket.client.host else "unknown"
    failure_key = f"{user_id}:{client_ip}"
    
    # Check rate limiting
    backoff_seconds = _get_ws_backoff_seconds(failure_key)
    if backoff_seconds > 0:
        logger.warning(f"WebSocket backoff activo para user_id={user_id}: {backoff_seconds}s")
        try:
            await websocket.accept()
            await _ws_send_json(
                websocket,
                {
                    "type": "error",
                    "message": "rate_limited",
                    "error_code": "rate_limited",
                    "retry_after_seconds": backoff_seconds,
                },
            )
            await websocket.close(code=1013)
        except Exception:
            pass
        return
    
    try:
        await websocket.accept()
        logger.info(f"WebSocket accepted for user_id={user_id}")
        
        # Authenticate
        try:
            token_user_id = await _ws_auth_user_id(websocket)
            _clear_ws_auth_failures(failure_key)
        except HTTPException as auth_http:
            failure_count = _track_ws_auth_failure(failure_key)
            retry_delay = _get_ws_backoff_seconds(failure_key)
            detail = getattr(auth_http, "detail", None)
            
            logger.warning(f"WebSocket auth failed ({detail}) for user_id={user_id}, failure_count={failure_count}")
            await _ws_send_json(
                websocket,
                {
                    "type": "error",
                    "message": str(detail),
                    "error_code": str(detail),
                    "requires_relogin": detail in {"token_expired", "token_revoked"},
                    "retry_after_seconds": retry_delay if detail not in {"token_expired", "token_revoked"} else None,
                },
            )
            await websocket.close(code=1008)
            return
        except Exception as auth_error:
            failure_count = _track_ws_auth_failure(failure_key)
            retry_delay = _get_ws_backoff_seconds(failure_key)
            logger.error(f"WebSocket AUTH FAILED for user_id={user_id}: {auth_error}")
            await _ws_send_json(
                websocket,
                {
                    "type": "error",
                    "message": "auth_failed",
                    "error_code": "auth_failed",
                    "retry_after_seconds": retry_delay,
                },
            )
            await websocket.close(code=1008)
            return
        
        # Verify user match
        if str(token_user_id) != str(user_id):
            logger.warning(f"User ID mismatch: token={token_user_id}, path={user_id}")
            await _ws_send_json(websocket, {"type": "error", "message": "forbidden_user_id_mismatch"})
            await websocket.close(code=1008)
            return

        decisions = await evaluate_rate_limits(
            namespace="chat_ws_connect",
            identifiers={
                "ip": websocket.client.host if websocket.client and websocket.client.host else "unknown",
                "user": str(token_user_id),
            },
            rules=_WS_CONNECT_RULES,
        )
        blocked = next((decision for decision in decisions if not decision.allowed), None)
        if blocked is not None:
            await _ws_send_json(
                websocket,
                {
                    "type": "error",
                    "message": "rate_limited",
                    "error_code": "rate_limited",
                    "scope": blocked.scope,
                    "retry_after_seconds": blocked.retry_after,
                },
            )
            await websocket.close(code=1013)
            return
        
        # Connection lock management
        conn_lock = get_user_ws_lock(user_id)
        if conn_lock.locked():
            if _ws_replace_existing_enabled():
                prev = get_active_ws(user_id)
                if prev is not None:
                    try:
                        await asyncio.wait_for(prev.close(code=1012), timeout=1.0)
                    except Exception:
                        pass
                await asyncio.sleep(0.05)
            else:
                await _ws_send_json(websocket, {"type": "error", "message": "ws_already_connected"})
                await websocket.close(code=1013)
                return
        
        # Acquire lock con timeout (prevenir bloqueo infinito en móviles)
        try:
            await asyncio.wait_for(conn_lock.acquire(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.error(f"WS lock timeout for user_id={user_id}")
            await _ws_send_json(websocket, {"type": "error", "message": "server_busy"})
            await websocket.close(code=1013)
            return
        
        set_active_ws(user_id, websocket)
        heartbeat_task = asyncio.create_task(_ws_heartbeat(websocket, str(user_id)))
        
        logger.info(f"WebSocket connected successfully for user_id={user_id}")
        
        # Capturar el bucle de eventos para streaming seguro desde hilos (Agentes)
        loop = asyncio.get_running_loop()
        
        # Debounce/Deduplicación de mensajes (Evitar repeticiones por ráfaga)
        last_msg_hash = None
        last_msg_time = 0.0
        connection_session_id: Optional[str] = None
        
        # Message loop
        while True:
            try:
                data = await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnect user_id={user_id}")
                break
            except Exception as e:
                logger.error(f"WebSocket receive error user_id={user_id}: {e}")
                break
            
            # Handle pong
            if data == "pong" or (data.startswith("{") and '"type":"pong"' in data):
                continue
            
            # Check message size
            if len(data) > _MAX_RAW_PAYLOAD_CHARS:
                await _ws_send_json(websocket, {"type": "error", "message": "payload_too_large"})
                try:
                    await websocket.close(code=1009)
                except Exception:
                    pass
                break
            
            # Parse JSON
            try:
                message_data = json.loads(data)
            except Exception as e:
                logger.warning(f"WebSocket invalid JSON user_id={user_id}: {e}")
                await _ws_send_json(websocket, {"type": "error", "message": "invalid_json"})
                continue

            if not isinstance(message_data, dict):
                await _ws_send_json(websocket, {"type": "error", "message": "invalid_message_payload"})
                continue

            if str(message_data.get("type") or "").strip().lower() == "pong":
                continue
            
            # DEDUPLICACIÓN: Evitar procesar el mismo mensaje en ráfaga (< 1.5s)
            msg_signature = _dedupe_signature(message_data)
            current_time = time.time()
            if msg_signature == last_msg_hash and (current_time - last_msg_time) < 1.5:
                logger.info(f"Deduplicación activa para user_id={user_id}: Ignorando mensaje repetido.")
                continue
            
            last_msg_hash = msg_signature
            last_msg_time = current_time

            # Process message
            resolved_session_id = await _process_chat_message(
                websocket,
                user_id,
                message_data,
                loop=loop,
                default_session_id=connection_session_id,
            )
            if resolved_session_id:
                connection_session_id = resolved_session_id
            
    except json.JSONDecodeError as e:
        logger.warning(f"WebSocket JSON decode error for user_id={user_id}: {e}")
    except Exception as e:
        logger.error(f"WebSocket ERROR for user_id={user_id}: {e}")
    finally:
        if conn_lock is not None and conn_lock.locked():
            try:
                conn_lock.release()
            except Exception:
                pass
        remove_active_ws(user_id, websocket)
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            logger.debug(f"Heartbeat task cancelled for user_id={user_id}")


async def _process_chat_message(
    websocket: WebSocket,
    user_id: str,
    message_data: Dict[str, Any],
    loop: Optional[asyncio.AbstractEventLoop] = None,
    default_session_id: Optional[str] = None,
) -> Optional[str]:
    """Process a single chat message from WebSocket"""
    from database import SessionLocal
    from models.models import ChatSession
    from services.chat_session_service import chat_session_service
    from routers.chat_search import _should_web_search, _should_include_images_in_search
    from services.agent_service import agent_manager
    from utils.agent_stream_bridge import run_agent_with_streaming
    from services.orchestration_service import scout
    import uuid
    
    start_ts = datetime.utcnow()
    request_id = uuid.uuid4().hex[:12]
    
    user_message = str(message_data.get("message", "") or "").strip()
    if _has_ws_attachment_payload(message_data):
        await _ws_send_json(
            websocket,
            {
                "type": "error",
                "message": "attachments_require_multipart_form_data",
                "error_code": "attachments_require_multipart_form_data",
                "upload_path": "/api/unified-chat/message",
                "request_id": request_id,
            },
        )
        return None

    if not user_message:
        await _ws_send_json(websocket, {"type": "error", "message": "message_empty"})
        return None
    
    if len(user_message) > _MAX_MESSAGE_CHARS:
        await _ws_send_json(websocket, {"type": "error", "message": f"message_too_long_max_{_MAX_MESSAGE_CHARS}"})
        return None

    force_web = _coerce_bool(message_data.get("web_search")) or _coerce_bool(message_data.get("search_web"))
    requested_session_id = _normalize_session_id(message_data.get("session_id"))
    fallback_session_id = _normalize_session_id(default_session_id)
    
    # ROOT RESOLUTION: Validate ownership and resolve session
    db = SessionLocal()
    try:
        session_id = requested_session_id or fallback_session_id
        session = None
        if session_id:
            session = chat_session_service.get_session(db, session_id=session_id, user_id=user_id)
            if session is None:
                if requested_session_id:
                    await _ws_send_json(websocket, {"type": "error", "message": "session_not_found", "request_id": request_id})
                    return None
                # If fallback failed, create new
                session = chat_session_service.create_session(db, user_id)
        else:
            session = chat_session_service.create_session(db, user_id)
        
        session_id = session.id
        
        # PERSIST USER MESSAGE (Atomic start)
        chat_session_service.add_message(
            db=db, session_id=session_id, user_id=user_id,
            role="user", content=user_message,
            media_metadata={},
            request_id=request_id
        )
    except Exception as e:
        logger.error(f"Root session resolution failure for user {user_id}: {e}")
        await _ws_send_json(websocket, {"type": "error", "message": "session_persistence_error", "request_id": request_id})
        return None
    finally:
        db.close()

    invalidate_user_context(user_id)
    await _ws_send_json(websocket, {"type": "session", "request_id": request_id, "session_id": session_id})

    # Get user context (NOW with SQL History)
    user_context = await get_user_context_for_chat(user_id, session_id=session_id)
    chat_history = user_context.get("chat_history", [])

    should_web_search = _should_web_search(
        user_id=user_id, message=user_message, force=force_web
    )
    effective_web_search = should_web_search
    logger.info(
        f"chat_ws_start request_id={request_id} user_id={user_id} "
        f"session_id={session_id} web_search={effective_web_search}"
    )

    # --- ORQUESTACIÓN AUTÓNOMA (Nivel Dios) ---
    # El Scout decide si necesitamos agentes o chat normal usando el HISTORIAL
    agent_input_message = user_message
    should_use_agents = scout.should_use_agents(agent_input_message, history=chat_history)
    if should_use_agents:
        task_desc = agent_input_message.strip()
        
        await _ws_send_status(websocket, "Activando equipo de investigacion academica...", request_id=request_id)
        
        # Callback para enviar tokens de los agentes al WebSocket
        def on_agent_token(token: str):
            target_loop = loop or asyncio.get_event_loop()
            asyncio.run_coroutine_threadsafe(
                _ws_send_json(websocket, {
                    "type": "token", 
                    "content": token,
                    "request_id": request_id,
                    "agent_mode": True
                }),
                target_loop
            )

        try:
            # Ejecutar el equipo de agentes con aislamiento de user_id
            # Aumentado a 120s para permitir tareas complejas y reintentos ante Error 429
            agent_timeout_s = int(os.getenv("AGENT_TIMEOUT_SECONDS", "120"))
            agent_result = await asyncio.wait_for(
                run_agent_with_streaming(
                    lambda: agent_manager.run_complex_task(task_desc, user_id=user_id, history=chat_history),
                    on_agent_token,
                ),
                timeout=agent_timeout_s,
            )
            agent_text = agent_manager.extract_text(agent_result)
            if agent_text:
                # Senior Persistent Flow
                await _persist_ws_session_turn(
                    user_id=user_id,
                    session_id=session_id,
                    ai_text=agent_text,
                    request_id=request_id,
                    user_message_for_naming=user_message
                )

                memory_id = str(uuid.uuid4())
                latency_ms = int((datetime.utcnow() - start_ts).total_seconds() * 1000)
                memory_debug = {
                    "latency_ms": latency_ms,
                    "query": user_message.strip(),
                    "agent_mode": True,
                }
                from utils.background import safe_create_task

                safe_create_task(
                    _persist_memory(user_id, memory_id, agent_text, [], user_message, memory_debug),
                    name=f"persist_agent_memory_{request_id}",
                )
                await _ws_send_json(
                    websocket,
                    {
                        "type": "complete",
                        "request_id": request_id,
                        "session_id": session_id,
                        "text": agent_text,
                        "memory_id": memory_id,
                        "sources": [],
                        "rich_response": None,
                        "agent_mode": True,
                    },
                )
            else:
                await _ws_send_json(
                    websocket,
                    {"type": "done", "request_id": request_id, "session_id": session_id, "agent_mode": True},
                )
            return session_id
        except asyncio.TimeoutError:
            logger.warning(f"Agent timeout request_id={request_id} user_id={user_id}")
            # El fallback a chat normal se encargará de completar la respuesta
            # Inyectamos una instrucción para que el chat normal no se presente si ya hubo actividad
            user_context["agent_timed_out"] = True 
            await _ws_send_status(
                websocket,
                "El equipo esta analizando mucha informacion. Continuare directamente para no hacerte esperar.",
                request_id=request_id,
            )
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            logger.error(f"Error en orquestación autónoma: {e}")
            
            # 1. Informar al usuario sutilmente
            await _ws_send_status(websocket, "Reajustando el equipo para continuar con la respuesta...", request_id=request_id)
            
            # 2. Información Técnica (Desarrollo)
            if DEBUG:
                await _ws_send_json(websocket, {
                    "type": "error", 
                    "message": "agent_failure", 
                    "detail": str(e),
                    "traceback": error_detail[-500:],
                    "request_id": request_id
                })
    
    # Web search
    ddg_sources: List[Dict[str, Any]] = []
    if effective_web_search:
        await _ws_send_status(websocket, "Buscando fuentes academicas actualizadas...", request_id=request_id)
        search_sources, _ = await perform_web_search(
            user_id=user_id,
            query=user_message.strip(),
            include_images=_should_include_images_in_search(user_message)
        )
        ddg_sources = prioritize_sources_with_images(search_sources, max_sources=5)
        if search_sources:
            user_context = dict(user_context)
            user_context["web_search_results"] = list(search_sources)[:5]
    
    # YouTube processing
    yt_video_id = youtube_transcript_service.extract_video_id(user_message)
    yt_source = None
    if yt_video_id:
        await _ws_send_status(websocket, "Leyendo transcripción de YouTube...", request_id=request_id)
        yt = await youtube_transcript_service.fetch_transcript_text(video_id=yt_video_id)
        if isinstance(yt, dict) and str(yt.get("text") or "").strip():
            user_context = dict(user_context)
            user_context["youtube_transcript"] = str(yt.get("text") or "")
            yt_source = youtube_transcript_service.build_source(
                video_id=yt_video_id,
                snippet=str(yt.get("text") or "")[:400],
            )
            if isinstance(yt_source, dict) and "style" not in yt_source:
                yt_source["style"] = "video"
    
    # Browser processing
    web_source = None
    if browser_mcp_service.enabled() and not yt_video_id:
        url = browser_mcp_service.extract_first_url(user_message)
        if url:
            await _ws_send_status(websocket, "Leyendo página web...", request_id=request_id)
            extracted = await browser_mcp_service.fetch_page_extract(url=url)
            if isinstance(extracted, dict) and str(extracted.get("text") or "").strip():
                user_context = dict(user_context)
                user_context["web_extract"] = str(extracted.get("text") or "")
                web_source = browser_mcp_service.build_source(
                    url=str(extracted.get("url") or url),
                    title=str(extracted.get("title") or ""),
                    snippet=str(extracted.get("text") or "")[:400],
                )
    
    # Send rich preview
    await _send_rich_preview(websocket, ddg_sources, yt_source, web_source, request_id)
    
    # AI streaming response
    await _ws_send_status(websocket, "Generando respuesta...", request_id=request_id)
    try:
        ai_result = await get_ai_response_with_streaming(
            user_id, user_message, user_context, websocket, request_id, 
            images=None, documents=None
        )
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.exception(f"WebSocket streaming error user_id={user_id}: {e}")
        
        # 1. Mensaje Pedagógico (Voz de Iris)
        pedagogical_msg = (
            "\nHubo un problema procesando esta solicitud. "
            "Intenta reformular la pregunta y continuamos desde ahi."
        )
        await _ws_send_json(websocket, {"type": "token", "content": pedagogical_msg, "request_id": request_id})
        
        # 2. Información Técnica (Solo para Desarrollo)
        if DEBUG:
            await _ws_send_json(websocket, {
                "type": "error", 
                "message": "debug_info", 
                "detail": str(e),
                "traceback": error_detail[-500:], # Últimos 500 caracteres para no saturar
                "request_id": request_id
            })
        return None
    
    text = str(ai_result.get("text") or "")
    logger.info(f"chat_ws_done request_id={request_id} user_id={user_id} response_len={len(text)}")
    
    # Save memory and persist
    memory_id = str(uuid.uuid4())
    latency_ms = int((datetime.utcnow() - start_ts).total_seconds() * 1000)
    memory_debug = {"latency_ms": latency_ms, "query": user_message.strip()}
    
    # PERSISTENCE: Save AI response and detect naming need
    # Senior Persistent Flow
    await _persist_ws_session_turn(
        user_id=user_id,
        session_id=session_id,
        ai_text=text,
        request_id=request_id,
        user_message_for_naming=user_message
    )
    
    from utils.background import safe_create_task
    final_sources_raw: List[Dict[str, Any]] = []
    if isinstance(yt_source, dict):
        final_sources_raw.append(yt_source)
    if isinstance(web_source, dict):
        final_sources_raw.append(web_source)
    final_sources_raw.extend(list(ddg_sources or []))

    safe_create_task(
        _persist_memory(user_id, memory_id, text, final_sources_raw, user_message, memory_debug),
        name=f"persist_memory_{request_id}",
    )
    
    # Send complete response
    sources = await _sanitize_sources_images(list(final_sources_raw or []))
    rich_response = _build_rich_response(text=text, memory_id=memory_id, sources=sources)
    
    await _ws_send_json(
        websocket,
        {
            "type": "complete",
            "request_id": request_id,
            "session_id": session_id,
            "text": text,
            "memory_id": memory_id,
            "sources": sources,
            "rich_response": rich_response.model_dump() if rich_response else None,
        },
    )
    return session_id


async def _send_rich_preview(
    websocket: WebSocket,
    ddg_sources: List[Dict[str, Any]],
    yt_source: Optional[Dict],
    web_source: Optional[Dict],
    request_id: str
):
    """Send rich preview with sources before AI response"""
    try:
        preview_sources: List[Dict[str, Any]] = []
        if isinstance(ddg_sources, list) and ddg_sources:
            preview_sources = list(ddg_sources)
        
        combined_preview: List[Dict[str, Any]] = []
        if isinstance(yt_source, dict):
            combined_preview.append(yt_source)
        if isinstance(web_source, dict):
            combined_preview.append(web_source)
        combined_preview.extend(list(preview_sources or []))
        
        if not combined_preview:
            return
        
        preview_sources = combined_preview[:5]
        preview_sources = await _sanitize_sources_images(list(preview_sources or []))
        
        rich_preview = _build_rich_response(text="", memory_id=None, sources=preview_sources)
        if rich_preview is not None:
            await _ws_send_json(
                websocket,
                {
                    "type": "rich",
                    "request_id": str(request_id),
                    "sources": preview_sources,
                    "rich_response": rich_preview.model_dump(),
                },
            )
    except Exception as e:
        logger.warning(f"ws_rich_preview_failed: {e}")


async def _persist_memory(
    user_id: str,
    memory_id: str,
    text: str,
    sources: List[Dict[str, Any]],
    query: str,
    debug: Dict[str, Any]
):
    """Persist memory to hub in background"""
    try:
        await hub_memory_service.save_memory(
            user_id=user_id,
            memory_id=memory_id,
            text=text,
            sources=sources,
            query=query,
            debug=debug,
        )
    except Exception as e:
        logger.warning(f"hub_memory_persist_failed: {e}")
