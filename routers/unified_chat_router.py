"""
Unified Chat Router Enterprise v5.0
Chat con IA + Voz + Monitoreo de Contexto Automático + Contexto de Tareas y Grabaciones
Diseñado para integración óptima con frontend
"""

import asyncio
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, date, timedelta
from urllib.parse import urlparse
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File, Depends, HTTPException, Request
from pydantic import BaseModel

from services.groq_ai_service import chat_with_ai, should_refresh_context, get_context_info, sanitize_ai_text
from services.groq_voice_service import transcribe_audio_groq, text_to_speech_groq
from utils.auth import get_current_user, verify_token
from models.models import SessionItem, RecordingSession
from sqlalchemy import select, and_

_WS_MAX_AUDIO_BYTES = 30 * 1024 * 1024
_WS_PARTIAL_INTERVAL_MS = 400
_WS_TAIL_WINDOW_MS = 4500

logger = logging.getLogger("unified_chat_router")

router = APIRouter(prefix="/unified-chat", tags=["Chat IA"])


def _new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def _safe_meta(meta: Any) -> Dict[str, Any]:
    if not isinstance(meta, dict):
        return {}
    out: Dict[str, Any] = {}
    for k in ("status", "attempt", "key_index", "fallback", "attempts"):
        if k in meta:
            out[k] = meta.get(k)
    return out


def _debug_enabled() -> bool:
    try:
        from config import DEBUG as CONFIG_DEBUG

        return bool(CONFIG_DEBUG)
    except Exception:
        return str(os.getenv("DEBUG") or "").strip() in {"1", "true", "True"}


def _user_requested_web_search(message: str) -> bool:
    msg = str(message or "").strip().lower()
    if not msg:
        return False
    return bool(
        re.search(
            r"\b(busca|buscar|buscame|búscame|investiga|investigar|search|googlea|googlear|web|en internet|en la web|muestrame|muéstrame|muestra|mostrar)\b",
            msg,
        )
    )


def _user_requested_images(message: str) -> bool:
    msg = str(message or "").strip().lower()
    if not msg:
        return False
    return bool(re.search(r"\b(imagen|imagenes|imágenes|foto|fotos|pictures|images)\b", msg))


def _should_include_images_in_search(message: str) -> bool:
    """Heurística: pedir imágenes aunque el usuario no diga literalmente 'imágenes'."""
    msg = str(message or "").strip()
    if not msg:
        return False
    lower = msg.lower()
    if _user_requested_images(lower):
        return True
    # Intención visual implícita
    if re.search(r"\b(c[óo]mo se ve|ver fotos|ver imagen|muestra(?:me)?|galer[ií]a|portada|logo|dise[ñn]o|captura|screenshot|wallpaper|fondo de pantalla)\b", lower):
        return True
    # Dominios donde la UI casi siempre se beneficia de imágenes
    if re.search(r"\b(hotel|hoteles|restaurante|restaurantes|resort|airbnb|producto|comprar|modelo|zapatillas|tenis|celular|m[oó]vil|laptop|pc|carro|auto|coche)\b", lower):
        return True
    return False


_last_auto_web_search_at: Dict[str, float] = {}


def _auto_web_search_enabled() -> bool:
    raw = os.getenv("AUTO_WEB_SEARCH_ENABLED")
    if raw is None:
        return True
    return str(raw).strip() in {"1", "true", "True"}


def _auto_web_search_cooldown_s() -> int:
    try:
        return int(os.getenv("AUTO_WEB_SEARCH_COOLDOWN_S", "25"))
    except Exception:
        return 25


def _heuristic_web_search_intent(message: str) -> bool:
    msg = str(message or "").strip()
    if not msg:
        return False
    lower = msg.lower()

    if _user_requested_web_search(lower) or _user_requested_images(lower):
        return True

    score = 0
    if "?" in msg:
        score += 1

    if re.search(r"\b(hoy|ayer|ultima|última|ultimas|últimas|noticia|noticias|actualiz|ahora|este año|este mes|202\d)\b", lower):
        score += 2
    if re.search(r"\b(qué pasó|que paso|pas[oó] con|incendio|se quem[oó]|accidente|terremoto|hurac[aá]n|explosi[oó]n)\b", lower):
        score += 2

    if re.search(r"\b(precio|cu[aá]nto cuesta|costo|tarifa|horario|direcci[oó]n|d[oó]nde queda|tel[eé]fono|reservar|disponibilidad)\b", lower):
        score += 2
    if re.search(r"\b(fuente|fuentes|link|enlace|seg[uú]n|verifica|confirmar)\b", lower):
        score += 2

    if len(lower) <= 80 and re.search(r"\b(hotel|restaurante|aeropuerto|universidad|clima|vuelos)\b", lower):
        score += 1

    return score >= 3


def _should_web_search(*, user_id: str, message: str) -> bool:
    if not _auto_web_search_enabled():
        return _user_requested_web_search(message) or _user_requested_images(message)

    if _user_requested_web_search(message) or _user_requested_images(message):
        return True

    if not _heuristic_web_search_intent(message):
        return False

    now = datetime.utcnow().timestamp()
    last = float(_last_auto_web_search_at.get(str(user_id)) or 0.0)
    if now - last < _auto_web_search_cooldown_s():
        return False
    _last_auto_web_search_at[str(user_id)] = now
    return True


def _semantic_cache_enabled() -> bool:
    raw = os.getenv("SEMANTIC_CACHE_ENABLED")
    if raw is None:
        return False
    return str(raw).strip() in {"1", "true", "True"}


def _should_use_semantic_cache(message: str) -> bool:
    msg = str(message or "").strip()
    if not msg:
        return False
    if not _semantic_cache_enabled():
        return False

    lower = msg.lower()
    if _heuristic_web_search_intent(lower) or _user_requested_web_search(lower) or _user_requested_images(lower):
        return False

    if re.search(r"\b(hoy|ayer|ultima|última|ultimas|últimas|noticia|noticias|actualiz|ahora|202\d)\b", lower):
        return False
    if re.search(r"\b(precio|cu[aá]nto cuesta|costo|tarifa|horario|direcci[oó]n|d[oó]nde queda|disponibilidad)\b", lower):
        return False

    return True

# =========================
# SCHEMAS
# =========================

class ChatMessageRequest(BaseModel):
    message: str
    files: Optional[List[str]] = None
    session_id: Optional[str] = None


class RichGalleryItem(BaseModel):
    title: str
    source: Optional[str] = None
    url: str
    image_url: Optional[str] = None
    style: Optional[str] = None


class RichResponse(BaseModel):
    type: str = "rich_response"
    text: str
    memory_id: Optional[str] = None
    gallery: Optional[List[RichGalleryItem]] = None
    suggestions: Optional[List[str]] = None

class ChatResponse(BaseModel):
    success: bool
    response: str
    user_id: str
    timestamp: str
    context: Optional[Dict[str, Any]] = None
    message_id: Optional[str] = None
    actions: Optional[List[Dict[str, Any]]] = None
    sources: Optional[List[Dict[str, Any]]] = None
    rich_response: Optional[RichResponse] = None

class VoiceChatResponse(BaseModel):
    success: bool
    transcribed: str
    response: str
    audio: str
    user_id: str
    timestamp: str
    message_id: Optional[str] = None

class ContextResponse(BaseModel):
    user_id: str
    usage_percent: float
    messages_count: int
    last_check: Optional[str] = None

class STTRequest(BaseModel):
    """Request para Speech-to-Text"""
    language: Optional[str] = "es"

class STTResponse(BaseModel):
    """Response de Speech-to-Text"""
    success: bool
    text: str
    language: str
    duration_ms: Optional[int] = None
    timestamp: str

class TTSRequest(BaseModel):
    """Request para Text-to-Speech"""
    text: str
    voice: Optional[str] = "male_1"
    speed: Optional[float] = 1.0
    language: Optional[str] = "es"

class TTSResponse(BaseModel):
    """Response de Text-to-Speech"""
    success: bool
    audio: str  # base64 data URI
    text: str
    voice: str
    timestamp: str

class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    error_code: str
    timestamp: str


async def _ws_auth_user_id(websocket: WebSocket) -> str:
    token = websocket.query_params.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="missing_token")
    payload = await verify_token(token, allow_expired_grace=True)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="invalid_token")
    return str(user_id)


def _ws_now_iso() -> str:
    return datetime.utcnow().isoformat()


def _estimate_duration_ms_from_bytes(audio_len: int) -> int:
    # Heurística: si llega PCM16 mono 16kHz => 32000 bytes/s
    # Si llega otro formato (webm/mp3), esto será sólo una aproximación.
    return int((audio_len / 32000.0) * 1000)


def _tail_bytes_for_pcm16(*, buf: bytearray, sample_rate: int, tail_window_ms: int) -> bytes:
    bytes_per_second = sample_rate * 2
    tail_len = int((tail_window_ms / 1000.0) * bytes_per_second)
    if tail_len <= 0:
        return bytes(buf)
    if tail_len >= len(buf):
        return bytes(buf)
    return bytes(buf[-tail_len:])


async def _ws_send_json(websocket: WebSocket, payload: Dict[str, Any]) -> None:
    try:
        from starlette.websockets import WebSocketState

        if websocket.client_state != WebSocketState.CONNECTED:
            return
        await websocket.send_text(json.dumps(payload, ensure_ascii=False))
    except Exception as e:
        try:
            from websockets.exceptions import ConnectionClosed
        except Exception:
            ConnectionClosed = None

        if ConnectionClosed is not None and isinstance(e, ConnectionClosed):
            return

        try:
            from starlette.websockets import WebSocketDisconnect
        except Exception:
            WebSocketDisconnect = None

        if WebSocketDisconnect is not None and isinstance(e, WebSocketDisconnect):
            return

        logger.error(f"Error sending WebSocket JSON: {e}")
        raise


def _host_label(url: str) -> str:
    try:
        host = (urlparse(url).netloc or "").strip()
        if host.startswith("www."):
            host = host[4:]
        return host or ""
    except Exception:
        return ""


def _is_supported_image_url(url: Optional[str]) -> bool:
    raw = str(url or "").strip()
    if not raw:
        return False
    try:
        p = urlparse(raw)
        if p.scheme not in {"http", "https"}:
            return False
        path = (p.path or "").lower()
        # Si no hay extensión, no lo bloqueamos (muchos CDNs sirven jpg sin extensión)
        if "." not in path.rsplit("/", 1)[-1]:
            return True
        ext = path.rsplit(".", 1)[-1]
        return ext in {"jpg", "jpeg", "png", "webp", "gif"}
    except Exception:
        return False


def _build_rich_response(*, text: str, memory_id: Optional[str], sources: Optional[List[Dict[str, Any]]]) -> Optional[RichResponse]:
    if not sources:
        return None

    gallery: List[RichGalleryItem] = []
    for s in sources:
        if not isinstance(s, dict):
            continue
        url = str(s.get("url") or "").strip()
        if not url:
            continue
        title = str(s.get("title") or s.get("name") or s.get("snippet") or "").strip() or url
        image_candidate = str(s.get("image") or s.get("image_url") or "").strip() or None
        image_url = image_candidate if _is_supported_image_url(image_candidate) else None
        source_label = str(s.get("source") or "").strip() or None
        if not source_label:
            host = _host_label(url)
            source_label = host or None
        style = str(s.get("style") or "").strip() or None
        gallery.append(
            RichGalleryItem(
                title=title,
                source=source_label,
                url=url,
                image_url=image_url,
                style=style,
            )
        )

    if not gallery:
        return None

    return RichResponse(
        text=str(text or "").strip(),
        memory_id=str(memory_id) if memory_id else None,
        gallery=gallery,
        suggestions=None,
    )


def _ws_status_enabled() -> bool:
    raw = os.getenv("WS_STATUS_ENABLED")
    if raw is None:
        return True
    return str(raw).strip() in {"1", "true", "True"}


async def _ws_send_status(websocket: WebSocket, content: str) -> None:
    if not _ws_status_enabled():
        return
    await _ws_send_json(
        websocket,
        {
            "type": "status",
            "content": str(content or "")[:200],
        },
    )

async def _ws_heartbeat(websocket: WebSocket):
    """Tarea en background para enviar pings y mantener la conexión activa."""
    try:
        while True:
            await asyncio.sleep(20)  # Cada 20 segundos (más frecuente para evitar timeout)
            try:
                # Verificar si la conexión sigue abierta antes de enviar
                from starlette.websockets import WebSocketState

                if websocket.client_state == WebSocketState.CONNECTED:
                    # Importante: NO enviar mensajes fuera del contrato (token/complete/error)
                    # El heartbeat queda como chequeo de conexión.
                    logger.debug("WS heartbeat check: connected")
            except Exception:
                # Conexión probablemente cerrada, salir del loop
                break
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning(f"WS heartbeat failed: {e}")

# =========================
# PERSISTENCIA DE PROGRESO
# =========================

_user_progress: Dict[str, Dict[str, Any]] = {}


def _sanitize_structured_data(structured_data: Any) -> Dict[str, Any]:
    if not isinstance(structured_data, dict):
        return {"tasks": [], "plan": [], "response": str(structured_data) if structured_data is not None else "", "is_stream": False}

    tasks_raw = structured_data.get("tasks")
    plan_raw = structured_data.get("plan")
    response_raw = structured_data.get("response")

    tasks: List[Dict[str, Any]] = []
    if isinstance(tasks_raw, list):
        for item in tasks_raw[:20]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            title = title[:200]
            priority = str(item.get("priority") or "medium").lower().strip()
            if priority not in {"high", "medium", "low"}:
                priority = "medium"
            due_date = item.get("due_date")
            due_date_out: Optional[str] = None
            if isinstance(due_date, str):
                s = due_date.strip()
                if s:
                    try:
                        date.fromisoformat(s)
                        due_date_out = s
                    except Exception:
                        due_date_out = None
            tasks.append({"title": title, "due_date": due_date_out, "priority": priority})

    plan: List[Dict[str, Any]] = []
    if isinstance(plan_raw, list):
        for step in plan_raw[:15]:
            if not isinstance(step, dict):
                continue
            step_text = str(step.get("step") or "").strip()
            if not step_text:
                continue
            duration = step.get("duration")
            duration_out: Optional[str] = None
            if isinstance(duration, str):
                d = duration.strip()
                duration_out = d[:60] if d else None
            plan.append({"step": step_text[:300], "duration": duration_out})

    response = ""
    if isinstance(response_raw, str):
        response = response_raw.strip()
    elif response_raw is not None:
        response = str(response_raw)
    response = response[:6000]
    
    # NO SANITIZAR - La IA responde libremente
    
    is_stream = bool(structured_data.get("is_stream", False))
    return {"tasks": tasks, "plan": plan, "response": response, "is_stream": is_stream}

async def save_user_progress(user_id: str, message: str, structured_data: Dict[str, Any]):
    """Guarda el progreso del usuario en memoria y persiste en DB (en producción usar Redis/DB)"""
    structured_data = _sanitize_structured_data(structured_data)
    if user_id not in _user_progress:
        _user_progress[user_id] = {
            "today_tasks": [],
            "week_tasks": [],
            "completed_tasks": [],
            "last_plan": [],
            "last_interaction": None
        }
    
    progress = _user_progress[user_id]
    progress["last_interaction"] = datetime.utcnow().isoformat()
    
    # Agregar nuevas tareas a la memoria
    for task in structured_data.get("tasks", []):
        if task.get("due_date"):
            try:
                task_date = date.fromisoformat(task["due_date"])
                today = date.today()
                if task_date == today:
                    if not any(t.get("title") == task.get("title") for t in progress["today_tasks"]):
                        progress["today_tasks"].append(task)
                elif task_date > today and task_date <= today + timedelta(days=7):
                    if not any(t.get("title") == task.get("title") for t in progress["week_tasks"]):
                        progress["week_tasks"].append(task)
            except Exception as e:
                logger.error(f"Error parsing task date: {e}")
    
    # Guardar plan en memoria
    if structured_data.get("plan"):
        progress["last_plan"] = structured_data["plan"]
        
    # Persistir en Base de Datos
    try:
        from database.db_enterprise import get_primary_session
        from models.models import SessionItem, RecordingSession, RecordingSessionType
        from sqlalchemy import select, and_
        
        db = await get_primary_session()
        async with db:
            # Asegurar que existe una sesión activa para este usuario para vincular las tareas
            stmt_session = select(RecordingSession).where(
                and_(
                    RecordingSession.user_id == user_id,
                    RecordingSession.title == "Chat Asistente"
                )
            ).order_by(RecordingSession.created_at.desc()).limit(1)
            result_session = await db.execute(stmt_session)
            active_session = result_session.scalar_one_or_none()

            if not active_session:
                active_session = RecordingSession(
                    user_id=user_id,
                    title="Chat Asistente",
                    session_type=RecordingSessionType.MANUAL,
                    status="completed",
                    transcript="Sesión de chat para persistencia de tareas"
                )
                db.add(active_session)
                await db.flush()

            for task in structured_data.get("tasks", []):
                title = task.get("title", "Tarea sin título")
                content = task.get("content", "")
                date_str = task.get("due_date")
                due_date_val = None
                if date_str:
                    try:
                        due_date_val = datetime.fromisoformat(date_str)
                    except (ValueError, TypeError): pass

                new_task = SessionItem(
                    user_id=user_id,
                    session_id=active_session.id,
                    title=title,
                    content=content,
                    due_date=due_date_val,
                    item_type="task",
                    status="suggested",
                    source="ai"
                )
                db.add(new_task)
            
            await db.commit()
            logger.info(f"✅ Progress and tasks persisted for user {user_id}")
    except Exception as e:
        logger.error(f"❌ Error persisting user progress: {e}")

    # Agregar acciones automáticas
    if structured_data.get("actions"):
        for action in structured_data["actions"]:
            action_type = action.get("type")
            action_data = action.get("data")
            if action_type == "schedule_class":
                logger.info(f"🤖 AI ACCIÓN AUTOMÁTICA: Agendando clase/evento - {action_data}")
                try:
                    from models.models import SessionItem
                    from database.db_enterprise import get_primary_session
                    db = await get_primary_session()
                    async with db:
                        # Buscar sesión de chat asistente unificada
                        from models.models import RecordingSession, RecordingSessionType
                        stmt_session = select(RecordingSession).where(
                            and_(
                                RecordingSession.user_id == user_id,
                                RecordingSession.title == "Chat Asistente"
                            )
                        ).order_by(RecordingSession.created_at.desc()).limit(1)
                        result_session = await db.execute(stmt_session)
                        active_session = result_session.scalar_one_or_none()

                        if not active_session:
                            active_session = RecordingSession(
                                user_id=user_id,
                                title="Chat Asistente",
                                session_type=RecordingSessionType.MANUAL,
                                status="completed",
                                transcript="Sesión de chat para acciones automáticas"
                            )
                            db.add(active_session)
                            await db.flush()

                        date_str = action_data.get("datetime") or action_data.get("date")
                        start_time_val = None
                        if date_str:
                            try:
                                start_time_val = datetime.fromisoformat(date_str)
                            except (ValueError, TypeError): pass

                        new_event = SessionItem(
                            user_id=user_id,
                            session_id=active_session.id,
                            title=action_data.get("title", "Evento sin título"),
                            content=action_data.get("description", ""),
                            datetime_start=start_time_val,
                            item_type="event",
                            status="confirmed",
                            source="ai"
                        )
                        db.add(new_event)
                        await db.commit()
                        logger.info(f"✅ Evento unificado persistido: {new_event.id}")
                except Exception as ex:
                    logger.error(f"Error persistiendo acción automática unificada: {ex}")


@router.get("/progress")
async def get_user_progress(user=Depends(get_current_user)):
    """Obtener progreso del usuario (hoy, semana, completado, último plan)"""
    user_id = user["user_id"]
    
    if user_id not in _user_progress:
        # Cargar desde DB si está disponible
        user_context = await _get_user_full_context(user_id)
        return {
            "success": True,
            "today_tasks": user_context.get("tasks_today", []),
            "week_tasks": user_context.get("tasks_upcoming", []),
            "completed_tasks": [],
            "last_plan": [],
            "last_interaction": None
        }
    
    progress = _user_progress[user_id]
    return {
        "success": True,
        "today_tasks": progress.get("today_tasks", []),
        "week_tasks": progress.get("week_tasks", []),
        "completed_tasks": progress.get("completed_tasks", []),
        "last_plan": progress.get("last_plan", []),
        "last_interaction": progress.get("last_interaction")
    }


@router.post("/progress/complete/{task_id}")
async def complete_task(task_id: str, user=Depends(get_current_user)):
    """Marcar tarea como completada"""
    user_id = user["user_id"]
    
    if user_id in _user_progress:
        progress = _user_progress[user_id]
        
        # Buscar y mover a completadas
        for task_list in ["today_tasks", "week_tasks"]:
            for i, task in enumerate(progress.get(task_list, [])):
                if task.get("id") == task_id:
                    progress["completed_tasks"].append({
                        **task,
                        "completed_at": datetime.utcnow().isoformat()
                    })
                    progress[task_list].pop(i)
                    break
    
    return {"success": True, "message": "Tarea completada"}


@router.post("/progress/plan")
async def save_plan(plan: List[Dict[str, Any]], user=Depends(get_current_user)):
    """Guardar plan de estudio"""
    user_id = user["user_id"]

    # Sanitizar plan recibido por cliente
    safe_plan: List[Dict[str, Any]] = []
    if isinstance(plan, list):
        for step in plan[:15]:
            if not isinstance(step, dict):
                continue
            step_text = str(step.get("step") or "").strip()
            if not step_text:
                continue
            duration = step.get("duration")
            duration_out: Optional[str] = None
            if isinstance(duration, str):
                d = duration.strip()
                duration_out = d[:60] if d else None
            safe_plan.append({"step": step_text[:300], "duration": duration_out})
    
    if user_id not in _user_progress:
        _user_progress[user_id] = {
            "today_tasks": [],
            "week_tasks": [],
            "completed_tasks": [],
            "last_plan": [],
            "last_interaction": None
        }
    
    _user_progress[user_id]["last_plan"] = safe_plan
    _user_progress[user_id]["last_interaction"] = datetime.utcnow().isoformat()
    
    return {"success": True, "message": "Plan guardado"}


@router.get("/progress/stats")
async def get_progress_stats(user=Depends(get_current_user)):
    """Obtener estadísticas de progreso del usuario"""
    user_id = user["user_id"]
    
    # Obtener datos de la DB
    user_context = await _get_user_full_context(user_id)
    
    completed_today = 0
    total_today = len(user_context.get("tasks_today", []))
    
    return {
        "success": True,
        "stats": {
            "tasks_today": total_today,
            "tasks_completed_today": completed_today,
            "tasks_upcoming": len(user_context.get("tasks_upcoming", [])),
            "completion_rate": round(completed_today / max(total_today, 1) * 100, 1)
        }
    }

# =========================
# FUNCIONES DE CONTEXTO
# =========================
 
async def _get_user_full_context(user_id: str) -> Dict[str, Any]:
    # REDEPLOY 2026-03-12: Fixed enum values - using lowercase 'task' and 'done'
    """Obtiene contexto completo del usuario: tareas + sesiones recientes"""
    from sqlalchemy import and_, select
    from models.models import User
    from models.models import SessionItem, RecordingSession
    
    context = {
        "tasks_today": [],
        "tasks_upcoming": [],
        "recent_sessions": [],
        "key_points_recent": []
    }
    
    try:
        from database.db_enterprise import get_primary_session
        db = await get_primary_session()
        async with db:
            today = date.today()
            end_week = today + timedelta(days=7)
            
            try:
                try:
                    stmt_user = select(User).where(User.id == user_id).limit(1)
                    result_user = await db.execute(stmt_user)
                    user_row = result_user.scalar_one_or_none()
                    if user_row is not None:
                        context["user_full_name"] = str(getattr(user_row, "full_name", "") or "").strip()
                except Exception:
                    pass

                # Tareas de hoy - use lowercase string literals
                stmt_tasks_today = select(SessionItem).where(
                    and_(
                        SessionItem.user_id == user_id,
                        SessionItem.item_type == "task",
                        SessionItem.due_date >= datetime.combine(today, datetime.min.time()),
                        SessionItem.status != "done",
                    )
                ).limit(10)
                result = await db.execute(stmt_tasks_today)
                tasks_today = result.scalars().all()
                context["tasks_today"] = [
                    {"id": t.id, "title": t.title, "due_date": t.due_date.isoformat() if t.due_date else None}
                    for t in tasks_today
                ]

                # Tareas próximas (próxima semana) - use lowercase string literals
                stmt_tasks_upcoming = select(SessionItem).where(
                    and_(
                        SessionItem.user_id == user_id,
                        SessionItem.item_type == "task",
                        SessionItem.due_date >= datetime.combine(today, datetime.min.time()),
                        SessionItem.due_date < datetime.combine(end_week, datetime.max.time()),
                        SessionItem.status != "done",
                    )
                ).order_by(SessionItem.due_date).limit(10)
                result = await db.execute(stmt_tasks_upcoming)
                tasks_upcoming = result.scalars().all()
                context["tasks_upcoming"] = [
                    {"id": t.id, "title": t.title, "due_date": t.due_date.isoformat() if t.due_date else None}
                    for t in tasks_upcoming
                ]

                # Puntos clave recientes - use lowercase string literals
                stmt_points = select(SessionItem).where(
                    and_(
                        SessionItem.user_id == user_id,
                        SessionItem.item_type == "key_point",
                        SessionItem.created_at
                        >= datetime.combine(today - timedelta(days=7), datetime.min.time()),
                    )
                ).limit(5)
                result = await db.execute(stmt_points)
                points = result.scalars().all()
                context["key_points_recent"] = [
                    {"id": p.id, "content": p.content[:100], "created_at": p.created_at.isoformat()}
                    for p in points
                ]
            except Exception as e:
                msg = str(e)
                if "relation \"session_items\" does not exist" in msg:
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    context["tasks_today"] = []
                    context["tasks_upcoming"] = []
                    context["key_points_recent"] = []
                else:
                    # Defensive rollback: evita que la transacción quede abortada y rompa el resto del contexto.
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    context["tasks_today"] = []
                    context["tasks_upcoming"] = []
                    context["key_points_recent"] = []
            
            try:
                stmt_sessions = select(RecordingSession).where(
                    and_(
                        RecordingSession.user_id == user_id,
                        RecordingSession.transcript.isnot(None),
                        RecordingSession.transcript != ""
                    )
                ).order_by(RecordingSession.created_at.desc()).limit(3)
                result = await db.execute(stmt_sessions)
                sessions = result.scalars().all()
                context["recent_sessions"] = [
                    {"id": s.id, "title": s.title, "date": s.created_at.isoformat()}
                    for s in sessions
                ]
            except Exception as e:
                msg = str(e)
                if "relation \"recording_sessions\" does not exist" in msg:
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    context["recent_sessions"] = []
                else:
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    context["recent_sessions"] = []
    except Exception as e:
        logger.error(f"Error al obtener contexto de usuario: {e}")
        
    
    return context


async def get_user_context_for_chat(user_id: str) -> Dict[str, Any]:
    """Contexto requerido por chat (HTTP y WebSocket)."""
    context = await _get_user_full_context(user_id)

    # Enriquecer con progreso en memoria si existe
    progress = _user_progress.get(user_id)
    if isinstance(progress, dict) and progress.get("last_plan"):
        context["last_plan"] = progress.get("last_plan")

    return context


def build_context_prompt(user_context: Dict[str, Any]) -> str:
    """Construye el prompt de contexto para la IA"""
    prompt_parts = []

    user_full_name = str(user_context.get("user_full_name") or "").strip()
    if user_full_name:
        prompt_parts.append(f"👤 USUARIO: {user_full_name}")
    
    if user_context.get("tasks_today"):
        prompt_parts.append("📋 TAREAS DE HOY:")
        for t in user_context["tasks_today"]:
            due = f" (fecha: {t['due_date']})" if t.get("due_date") else ""
            prompt_parts.append(f"  - {t['title']}{due}")
    
    if user_context.get("tasks_upcoming"):
        prompt_parts.append("\n📅 TAREAS PRÓXIMAS:")
        for t in user_context["tasks_upcoming"][:5]:
            due = f" (fecha: {t['due_date']})" if t.get("due_date") else ""
            prompt_parts.append(f"  - {t['title']}{due}")
    
    key_points = user_context.get("key_points") or user_context.get("key_points_recent")
    if key_points:
        prompt_parts.append("\n🔑 PUNTOS CLAVE DE CLASES RECIENTES:")
        for p in key_points:
            if not isinstance(p, dict):
                prompt_parts.append(f"  - {str(p)[:100]}...")
                continue
            title = str(p.get("title") or "").strip()
            content = str(p.get("content") or "")
            if title:
                prompt_parts.append(f"  - {title}: {content[:100]}...")
            else:
                prompt_parts.append(f"  - {content[:100]}...")
    
    if user_context.get("recent_sessions"):
        prompt_parts.append("\n🎓 SESIONES RECIENTES:")
        for s in user_context["recent_sessions"]:
            if not isinstance(s, dict):
                prompt_parts.append(f"  - {str(s)[:120]}")
                continue
            class_name = str(s.get("class_name") or "").strip()
            topic = s.get("topic")
            title = str(s.get("title") or "").strip()
            date_val = s.get("date")
            if class_name:
                topic_text = "Sin tema"
                if isinstance(topic, str) and topic.strip():
                    topic_text = topic.strip()
                prompt_parts.append(f"  - {class_name}: {topic_text[:120]}")
                continue
            if title:
                suffix = f" ({date_val})" if isinstance(date_val, str) and date_val.strip() else ""
                prompt_parts.append(f"  - {title[:200]}{suffix}")
                continue
            prompt_parts.append(f"  - {str(s)[:120]}")

    yt_transcript = str(user_context.get("youtube_transcript") or "").strip()
    if yt_transcript:
        prompt_parts.append("\n🎥 TRANSCRIPCIÓN YOUTUBE (extracto):")
        prompt_parts.append(yt_transcript[:500])

    web_extract = str(user_context.get("web_extract") or "").strip()
    if web_extract:
        prompt_parts.append("\n🌐 EXTRACTO WEB (texto visible):")
        prompt_parts.append(web_extract[:500])

    web_search_results = user_context.get("web_search_results")
    if isinstance(web_search_results, list) and web_search_results:
        prompt_parts.append("\n🔎 RESULTADOS WEB (DuckDuckGo):")
        if user_context.get("web_search_images_requested"):
            prompt_parts.append("- Nota: el usuario pidió imágenes. Describe lo que se ve usando los thumbnails/imagenes y snippets.")
        for r in web_search_results[:3]:
            if not isinstance(r, dict):
                continue
            title = str(r.get("title") or "").strip()[:120]
            url = str(r.get("url") or "").strip()[:300]
            snippet = str(r.get("snippet") or "").strip()[:220]
            line = "- "
            if title:
                line += title
            if url:
                line += f" ({url})"
            if snippet:
                line += f" — {snippet}"
            prompt_parts.append(line[:700])

    web_search_status = str(user_context.get("web_search_status") or "").strip()
    if web_search_status:
        prompt_parts.append("\n🔎 ESTADO BÚSQUEDA WEB:")
        prompt_parts.append(f"- {web_search_status}")
    
    if prompt_parts:
        return "INFORMACIÓN DEL USUARIO:\n" + "\n".join(prompt_parts) + "\n\n"
    return ""


# =========================
# ENDPOINTS
# =========================

async def get_ai_response_with_streaming(
    user_id: str,
    message: str,
    user_context: Dict[str, Any],
    websocket: WebSocket
) -> Dict[str, Any]:
    """Streaming REAL: Envía tokens uno por uno al WebSocket."""
    from services.groq_ai_service import chat_with_ai, sanitize_ai_text
    
    context_prompt = build_context_prompt(user_context)

    user_full_name = str(user_context.get("user_full_name") or "").strip()
    user_name_line = f"El usuario se llama {user_full_name}. Dirígete a él/ella por su nombre.\n" if user_full_name else ""

    msg_low = str(message or "").strip().lower()
    wants_detail = any(
        k in msg_low
        for k in (
            "explica",
            "explicame",
            "explícame",
            "detalle",
            "detalles",
            "a detalle",
            "paso a paso",
            "por que",
            "por qué",
            "porque",
            "como funciona",
            "cómo funciona",
            "mas profundo",
            "más profundo",
        )
    )
    
    # Prompt que fuerza texto plano (sin JSON) para respetar el contrato WS
    system_content = (
        "Eres la Extensión Cognitiva del usuario.\n"
        + user_name_line
        + (
            "El usuario pidió explicación: puedes responder con más detalle, pero sé directo (máximo 10-14 líneas).\n"
            "Usa: 1 frase + 3-6 viñetas.\n"
            if wants_detail
            else "Responde corto por defecto: máximo 2-4 líneas, o 3 viñetas cortas.\n"
        )
        + "No escribas artículos largos. No repitas la pregunta.\n\n"
        + "ESTILO:\n"
        + "• Cero saludos innecesarios. Cero relleno.\n"
        + "• Acción inmediata: el usuario habla, tú ejecutas.\n"
        + "• Usa emojis solo si son 1 y aportan valor.\n"
        + "• Tono: confidente, proactivo, sin disculpas.\n\n"
        + "TUS PODERES SOBRE LA BASE DE DATOS:\n"
        + "• Crear tareas automáticamente con título, fecha y prioridad.\n"
        + "• Agendar clases recurrentes (fines de semana, horarios fijos).\n"
        + "• Activar grabaciones de audio automáticamente.\n"
        + "• Generar documentos APA7, resúmenes, puntos clave.\n"
        + "• Recordar TODO: nombres, fechas, preferencias, historial académico.\n\n"
        + "FORMATO DE RESPUESTA (OBLIGATORIO):\n"
        + "- Devuelve ÚNICAMENTE texto plano.\n"
        + "- NO incluyas JSON, XML, Markdown ni bloques de código.\n"
        + "REGLA DE ORO: Ejecuta inmediatamente. Cero confirmaciones.\n"
    )

    if context_prompt:
        system_content += "\n\n" + context_prompt
    
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": message}
    ]
    
    # Acumulador de texto completo
    full_text = ""

    try:
        overall_timeout_s = float(os.getenv("WS_LLM_STREAM_OVERALL_TIMEOUT_S", "120") or "120")
    except Exception:
        overall_timeout_s = 120.0

    stream_started_at = time.monotonic()
    first_token_at: Optional[float] = None

    try:
        import anyio

        stream_generator = await chat_with_ai(
            messages=messages,
            user=user_id,
            fast_reasoning=True,
            stream=True,
        )

        with anyio.fail_after(overall_timeout_s):
            async for chunk in stream_generator:
                if not chunk:
                    continue

                if first_token_at is None:
                    first_token_at = time.monotonic()
                    logger.info(
                        f"llm_ws_first_token user_id={user_id} latency_ms={int((first_token_at-stream_started_at)*1000)}"
                    )

                full_text += chunk
                await _ws_send_json(
                    websocket,
                    {
                        "type": "token",
                        "content": chunk,
                        "token": chunk,
                    },
                )

    except asyncio.TimeoutError as e:
        logger.error(
            f"llm_ws_stream_timeout user_id={user_id} elapsed_ms={int((time.monotonic()-stream_started_at)*1000)} err={e}"
        )
        raise
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        raise

    return {
        "text": sanitize_ai_text(full_text or ""),
    }


@router.post("/message", response_model=ChatResponse)
async def unified_chat_message(
    message: str,
    files: Optional[List[UploadFile]] = File(None),
    user: dict = Depends(get_current_user),
    stream: bool = False,
):
    """Chat con IA - incluye contexto de tareas y grabaciones"""
    
    try:
        user_id = user["user_id"]
        request_id = _new_request_id()
        t0 = time.monotonic()
        logger.info(
            f"chat_http_start request_id={request_id} user_id={user_id} message_len={len(message or '')} images={_user_requested_images(message)} web_search={_should_web_search(user_id=user_id, message=message)}"
        )
        
        # Pareto 80/20: Intentar obtener respuesta del cache semántico
        from services.embeddings_service import embeddings_service
        cached_response = None
        if _should_use_semantic_cache(message):
            cached_response = await embeddings_service.get_cached_response(message)
        
        if cached_response and not stream:
            # Si hay cache hit, retornamos inmediatamente (latencia < 50ms)
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
        
        # Obtener contexto del usuario
        user_context = await get_user_context_for_chat(user_id)

        # Web search (Tavily -> Serper -> DDG) cuando aplique (incluye petición de imágenes)
        ddg_sources: List[Dict[str, Any]] = []
        if _should_web_search(user_id=user_id, message=message):
            ws_t0 = time.monotonic()
            from services.ddg_search_service import ddg_search_service
            from services.tavily_search_service import tavily_search_service
            from services.serper_search_service import serper_search_service

            include_images = _should_include_images_in_search(message)

            ddg_meta: Dict[str, Any] = {"status": "skipped"}
            tavily_sources: List[Dict[str, Any]] = []
            tavily_meta: Dict[str, Any] = {"status": "disabled"}
            if tavily_search_service.enabled():
                try:
                    tavily_sources, tavily_meta = await tavily_search_service.search_with_meta(
                        query=message.strip(),
                        user_id=str(user_id),
                        include_images=include_images,
                    )
                except Exception:
                    tavily_sources = []
                    tavily_meta = {"status": "failed"}

            if tavily_sources:
                ddg_sources = list(tavily_sources)
                logger.info(
                    f"web_search_provider request_id={request_id} user_id={user_id} provider=tavily meta={_safe_meta(tavily_meta)} results={len(ddg_sources)} duration_ms={int((time.monotonic()-ws_t0)*1000)}"
                )
                user_context = dict(user_context)
                user_context["web_search_results"] = list(ddg_sources or [])[:5]
                if include_images:
                    user_context["web_search_images_requested"] = True
            else:
                serper_meta: Dict[str, Any] = {"status": "disabled"}
                if serper_search_service.enabled():
                    try:
                        ddg_sources, serper_meta = await serper_search_service.search_with_meta(
                            query=message.strip(),
                            user_id=str(user_id),
                            include_images=include_images,
                        )
                    except Exception:
                        ddg_sources = []
                        serper_meta = {"status": "failed"}

                if ddg_sources:
                    logger.info(
                        f"web_search_provider request_id={request_id} user_id={user_id} provider=serper meta={_safe_meta(serper_meta)} results={len(ddg_sources)} duration_ms={int((time.monotonic()-ws_t0)*1000)}"
                    )

                if not ddg_sources:
                    try:
                        ddg_sources, ddg_meta = await ddg_search_service.search_with_meta(message.strip())
                    except Exception:
                        ddg_sources = []
                        ddg_meta = {"status": "failed"}

                    logger.info(
                        f"web_search_provider request_id={request_id} user_id={user_id} provider=ddg meta={_safe_meta(ddg_meta)} results={len(ddg_sources)} duration_ms={int((time.monotonic()-ws_t0)*1000)}"
                    )

                if ddg_sources:
                    user_context = dict(user_context)
                    user_context["web_search_results"] = list(ddg_sources or [])[:5]
                    if include_images:
                        user_context["web_search_images_requested"] = True
                else:
                    status_val = None
                    if isinstance(tavily_meta, dict) and tavily_meta.get("status") not in (None, "ok"):
                        status_val = tavily_meta.get("status")
                    if status_val is None and isinstance(serper_meta, dict) and serper_meta.get("status") not in (None, "ok"):
                        status_val = serper_meta.get("status")
                    if status_val is None and isinstance(ddg_meta, dict) and ddg_meta.get("status") not in (None, "ok", "cache_hit"):
                        status_val = ddg_meta.get("status")
                    if status_val is not None:
                        user_context = dict(user_context)
                        user_context["web_search_status"] = str(status_val or "failed")

        # Priorizar thumbnails si el usuario pidió imágenes
        sources: List[Dict[str, Any]] = []
        if isinstance(ddg_sources, list) and ddg_sources:
            combined_sources = list(ddg_sources)
            max_sources = 5 if _user_requested_images(message) else 3
            if _user_requested_images(message):
                prioritized: List[Dict[str, Any]] = []
                remainder: List[Dict[str, Any]] = []
                for s in list(combined_sources):
                    if not isinstance(s, dict):
                        continue
                    if str(s.get("image") or "").strip():
                        prioritized.append(s)
                    else:
                        remainder.append(s)
                sources = (prioritized + remainder)[:max_sources]
            else:
                sources = list(combined_sources)[:max_sources]

        logger.info(
            f"chat_http_llm_start request_id={request_id} user_id={user_id} sources={len(sources)} web_results={len(list(user_context.get('web_search_results') or []))}"
        )

        # HTTP: usar modo no-streaming (más estable que emular WS con MockWebSocket)
        context_prompt = build_context_prompt(user_context)
        user_full_name = str(user_context.get("user_full_name") or "").strip()
        user_name_line = f"El usuario se llama {user_full_name}. Dirígete a él/ella por su nombre.\n" if user_full_name else ""
        msg_low = str(message or "").strip().lower()
        wants_detail = any(
            k in msg_low
            for k in (
                "explica",
                "explicame",
                "explícame",
                "detalle",
                "detalles",
                "a detalle",
                "paso a paso",
                "por que",
                "por qué",
                "porque",
                "como funciona",
                "cómo funciona",
                "mas profundo",
                "más profundo",
            )
        )
        system_content = (
            "Eres la Extensión Cognitiva del usuario.\n"
            + user_name_line
            + (
                "El usuario pidió explicación: puedes responder con más detalle, pero sé directo (máximo 10-14 líneas).\n"
                "Usa: 1 frase + 3-6 viñetas.\n"
                if wants_detail
                else "Responde corto por defecto: máximo 2-4 líneas, o 3 viñetas cortas.\n"
            )
            + "No escribas artículos largos. No repitas la pregunta.\n\n"
            + "ESTILO:\n"
            + "• Cero saludos innecesarios. Cero relleno.\n"
            + "• Acción inmediata: el usuario habla, tú ejecutas.\n"
            + "• Usa emojis solo si son 1 y aportan valor.\n"
            + "• Tono: confidente, proactivo, sin disculpas.\n\n"
            + "FORMATO DE RESPUESTA (OBLIGATORIO):\n"
            + "- Devuelve ÚNICAMENTE texto plano.\n"
            + "- NO incluyas JSON, XML, Markdown ni bloques de código.\n"
        )
        if context_prompt:
            system_content += "\n\n" + context_prompt
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": message},
        ]
        ai_text = await chat_with_ai(messages=messages, user=user_id, fast_reasoning=True, stream=False)
        structured = _sanitize_structured_data({"response": ai_text, "tasks": [], "plan": [], "actions": [], "is_stream": False})

        logger.info(
            f"chat_http_done request_id={request_id} user_id={user_id} duration_ms={int((time.monotonic()-t0)*1000)} response_len={len(structured.get('response') or '')}"
        )
        
        # Guardar progreso del usuario en background para no bloquear la respuesta
        asyncio.create_task(save_user_progress(user_id, message, structured))
        
        # Guardar en cache semántico para futuras consultas similares
        if not structured.get("is_stream"):
            await embeddings_service.add_to_semantic_cache(message, structured["response"])
        
        # Procesar acciones especiales (ej: agendar grabación)
        if structured.get("actions"):
            for action in structured["actions"]:
                action_type = action.get("type")
                action_data = action.get("data", {})
                
                if action_type == "schedule_class":
                    logger.info(f"🤖 AI ACCIÓN AUTOMÁTICA: Agendando clase/evento - {action_data}")
                    try:
                        from models.models import SessionItem, RecordingSession, RecordingSessionType
                        from database.db_enterprise import get_primary_session
                        db = await get_primary_session()
                        async with db:
                            # Asegurar sesión de chat asistente unificada
                            stmt_session = select(RecordingSession).where(
                                and_(
                                    RecordingSession.user_id == user_id,
                                    RecordingSession.title == "Chat Asistente"
                                )
                            ).order_by(RecordingSession.created_at.desc()).limit(1)
                            result_session = await db.execute(stmt_session)
                            active_session = result_session.scalar_one_or_none()

                            if not active_session:
                                active_session = RecordingSession(
                                    user_id=user_id,
                                    title="Chat Asistente",
                                    session_type=RecordingSessionType.MANUAL,
                                    status="completed"
                                )
                                db.add(active_session)
                                await db.flush()

                            # Mapear datos de la IA a campos de la DB
                            start_time_val = datetime.utcnow()
                            if action_data.get("start_time"):
                                try:
                                    date_str = action_data["start_time"].replace("Z", "").split(".")[0]
                                    start_time_val = datetime.fromisoformat(date_str)
                                except (ValueError, TypeError): pass

                            new_event = SessionItem(
                                user_id=user_id,
                                session_id=active_session.id,
                                title=action_data.get("title", "Evento sin título"),
                                item_type="event",
                                datetime_start=start_time_val,
                                content=f"Automatización: Grabación={action_data.get('recording', True)}, Recurrente={action_data.get('recurring', 'none')}. Participantes: {', '.join(action_data.get('participants', []))}",
                                status="confirmed",
                                priority="medium",
                                source="ai"
                            )
                            db.add(new_event)
                            await db.commit()
                            logger.info(f"✅ Ejecución silenciosa unificada exitosa: {action_type}")
                    except Exception as e:
                        logger.error(f"❌ Fallo en ejecución silenciosa unificada ({action_type}): {e}")

                elif action_type == "generate_document":
                    logger.info(f"🤖 AI ACCIÓN AUTOMÁTICA: Preparando documento - {action_data}")
                    try:
                        from services.document_service import create_document_from_user_message
                        asyncio.create_task(create_document_from_user_message(
                            user_message=action_data.get("content", message),
                            user_id=user_id,
                            doc_type=action_data.get("format", "pdf")
                        ))
                        logger.info(f"✅ Ejecución silenciosa iniciada: {action_type}")
                    except Exception as e:
                        logger.error(f"❌ Fallo al iniciar ejecución silenciosa ({action_type}): {e}")

        context_info = get_context_info(user_id)

        logger.info(
            f"chat_http_json_done request_id={request_id} user_id={user_id} duration_ms={int((time.monotonic()-t0)*1000)} response_len={len(structured.get('response') or '')} sources={len(list(sources or []))}"
        )

        message_id = f"msg_{datetime.utcnow().timestamp()}"
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
            rich_response=_build_rich_response(
                text=str(structured.get("response") or ""),
                memory_id=message_id,
                sources=sources if sources else None,
            ),
        )
        
    except RuntimeError as e:
        if "GROQ_API_KEY" in str(e):
            raise HTTPException(status_code=503, detail="llm_unavailable_missing_groq_api_key")
        raise
    except Exception as e:
        logger.exception("unified_chat_message_failed", extra={"user_id": str(user_id), "error": str(e)})
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": str(e),
                "error_code": "CHAT_ERROR",
                "timestamp": datetime.utcnow().isoformat()
            }
        )


@router.post("/stt", response_model=STTResponse)
async def stt_endpoint(
    audio: UploadFile = File(...),
    request: STTRequest = Depends(),
    user: dict = Depends(get_current_user),
):
    """Speech-to-Text (multipart)."""
    audio_bytes = await audio.read()
    audio_format = (audio.content_type or "")
    text = await transcribe_audio_groq(audio_bytes, language=request.language, audio_format=audio_format)
    return STTResponse(
        success=True,
        text=text,
        language=request.language or "",
        duration_ms=_estimate_duration_ms_from_bytes(len(audio_bytes)),
        timestamp=datetime.utcnow().isoformat(),
    )


@router.post("/tts", response_model=TTSResponse)
async def tts_endpoint(
    req: TTSRequest,
    user: dict = Depends(get_current_user),
):
    """Text-to-Speech (JSON)."""
    text = (req.text or "").strip()
    if not text or len(text) > 5000:
        raise HTTPException(status_code=400, detail="text_empty_or_too_long_max_5000")
    audio_uri = await text_to_speech_groq(text, voice=req.voice, speed=req.speed, language=req.language)
    return TTSResponse(
        success=True,
        audio=audio_uri,
        text=text,
        voice=req.voice or "",
        timestamp=datetime.utcnow().isoformat(),
    )


@router.post("/voice/message", response_model=VoiceChatResponse)
async def voice_message_http(
    audio: UploadFile = File(...),
    language: str = "es",
    voice: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Chat por voz via HTTP: STT -> LLM -> TTS."""
    user_id = user["user_id"]
    audio_bytes = await audio.read()
    if len(audio_bytes) > _WS_MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="audio_too_large_max_10mb")

    audio_format = (audio.content_type or "")
    transcribed = await transcribe_audio_groq(audio_bytes, language=language, audio_format=audio_format)

    user_context = await get_user_context_for_chat(user_id)
    
    # Mock WebSocket para capturar respuesta
    class MockWebSocket:
        def __init__(self):
            self.full_text = ""
        async def send_text(self, text):
            try:
                data = json.loads(text)
                if data["type"] == "token":
                    self.full_text += data["content"]
            except: pass
        async def send_json(self, data):
            if data.get("type") == "token":
                self.full_text += data.get("content", "")
        @property
        def client_state(self):
            from starlette.websockets import WebSocketState
            return type('State', (), {'CONNECTED': WebSocketState.CONNECTED})
            
    mock_ws = MockWebSocket()
    structured = await get_ai_response_with_streaming(user_id, transcribed, user_context, mock_ws)
    
    response_text = structured.get("text") if isinstance(structured, dict) else str(structured)
    
    audio_uri = await text_to_speech_groq(response_text, voice=voice, language=language)

    return VoiceChatResponse(
        success=True,
        transcribed=transcribed,
        response=response_text,
        audio=audio_uri,
        user_id=user_id,
        timestamp=datetime.utcnow().isoformat(),
        message_id=f"voice_{datetime.utcnow().timestamp()}",
    )


@router.post("/message/json", response_model=ChatResponse)
async def unified_chat_message_json(
    request: ChatMessageRequest,
    user: dict = Depends(get_current_user),
):
    """Chat con IA - versión JSON body con contexto estructurado y cache semántico"""
    
    try:
        user_id = user["user_id"]
        request_id = _new_request_id()
        t0 = time.monotonic()
        logger.info(
            f"chat_http_json_start request_id={request_id} user_id={user_id} message_len={len(request.message or '')} images={_user_requested_images(request.message)} web_search={_should_web_search(user_id=user_id, message=request.message)} session_id={str(request.session_id or '')}"
        )
        
        # Pareto 80/20: Intentar obtener respuesta del cache semántico
        from services.embeddings_service import embeddings_service
        cached_response = None
        if _should_use_semantic_cache(request.message):
            cached_response = await embeddings_service.get_cached_response(request.message)
        if cached_response:
            context_info = get_context_info(user_id)
            return ChatResponse(
                success=True,
                response=cached_response,
                user_id=user_id,
                timestamp=datetime.utcnow().isoformat(),
                context={
                    "usage_percent": round(context_info.get("usage", 0) * 100, 1),
                    "cache_hit": True,
                    "session_id": request.session_id
                },
                message_id=f"msg_cached_{datetime.utcnow().timestamp()}"
            )
        
        # Obtener contexto del usuario
        user_context = await get_user_context_for_chat(user_id)

        # `sources` must always be defined for the response contract
        sources: List[Dict[str, Any]] = []

        # Web search (Tavily -> Serper -> DDG) cuando aplique (incluye petición de imágenes)
        ddg_sources: List[Dict[str, Any]] = []
        if _should_web_search(user_id=user_id, message=request.message):
            ws_t0 = time.monotonic()
            from services.ddg_search_service import ddg_search_service
            from services.tavily_search_service import tavily_search_service
            from services.serper_search_service import serper_search_service

            ddg_meta: Dict[str, Any] = {"status": "skipped"}
            tavily_sources: List[Dict[str, Any]] = []
            tavily_meta: Dict[str, Any] = {"status": "disabled"}
            serper_meta: Dict[str, Any] = {"status": "disabled"}

            if tavily_search_service.enabled():
                try:
                    tavily_sources, tavily_meta = await tavily_search_service.search_with_meta(
                        query=str(request.message or "").strip(),
                        user_id=str(user_id),
                        include_images=_user_requested_images(request.message),
                    )
                except Exception:
                    tavily_sources = []
                    tavily_meta = {"status": "failed"}

            if tavily_sources:
                ddg_sources = list(tavily_sources)
                logger.info(
                    f"web_search_provider request_id={request_id} user_id={user_id} provider=tavily meta={_safe_meta(tavily_meta)} results={len(ddg_sources)} duration_ms={int((time.monotonic()-ws_t0)*1000)}"
                )
            else:
                if serper_search_service.enabled():
                    try:
                        ddg_sources, serper_meta = await serper_search_service.search_with_meta(
                            query=str(request.message or "").strip(),
                            user_id=str(user_id),
                            include_images=_user_requested_images(request.message),
                        )
                    except Exception:
                        ddg_sources = []
                        serper_meta = {"status": "failed"}

                if ddg_sources:
                    logger.info(
                        f"web_search_provider request_id={request_id} user_id={user_id} provider=serper meta={_safe_meta(serper_meta)} results={len(ddg_sources)} duration_ms={int((time.monotonic()-ws_t0)*1000)}"
                    )

                if not ddg_sources:
                    try:
                        ddg_sources, ddg_meta = await ddg_search_service.search_with_meta(
                            str(request.message or "").strip(),
                            prefer_images=_user_requested_images(request.message),
                        )
                    except TypeError:
                        ddg_sources, ddg_meta = await ddg_search_service.search_with_meta(
                            str(request.message or "").strip()
                        )
                    except Exception:
                        ddg_sources = []
                        ddg_meta = {"status": "failed"}

                    logger.info(
                        f"web_search_provider request_id={request_id} user_id={user_id} provider=ddg meta={_safe_meta(ddg_meta)} results={len(ddg_sources)} duration_ms={int((time.monotonic()-ws_t0)*1000)}"
                    )

            if ddg_sources:
                user_context = dict(user_context)
                user_context["web_search_results"] = list(ddg_sources or [])[:5]
                if _user_requested_images(request.message):
                    user_context["web_search_images_requested"] = True

                max_sources = 5 if _user_requested_images(request.message) else 3
                if _user_requested_images(request.message):
                    prioritized: List[Dict[str, Any]] = []
                    remainder: List[Dict[str, Any]] = []
                    for s in list(ddg_sources):
                        if not isinstance(s, dict):
                            continue
                        if str(s.get("image") or "").strip():
                            prioritized.append(s)
                        else:
                            remainder.append(s)
                    sources = (prioritized + remainder)[:max_sources]
                else:
                    sources = list(ddg_sources)[:max_sources]
            else:
                status_val = None
                if isinstance(tavily_meta, dict) and tavily_meta.get("status") not in (None, "ok"):
                    status_val = tavily_meta.get("status")
                if status_val is None and isinstance(serper_meta, dict) and serper_meta.get("status") not in (None, "ok"):
                    status_val = serper_meta.get("status")
                if status_val is None and isinstance(ddg_meta, dict) and ddg_meta.get("status") not in (None, "ok", "cache_hit"):
                    status_val = ddg_meta.get("status")
                if status_val is not None:
                    user_context = dict(user_context)
                    user_context["web_search_status"] = str(status_val or "failed")

        # HTTP JSON: usar modo no-streaming + mismo prompt adaptativo que WS/HTTP
        context_prompt = build_context_prompt(user_context)
        user_full_name = str(user_context.get("user_full_name") or "").strip()
        user_name_line = f"El usuario se llama {user_full_name}. Dirígete a él/ella por su nombre.\n" if user_full_name else ""
        msg_low = str(request.message or "").strip().lower()
        wants_detail = any(
            k in msg_low
            for k in (
                "explica",
                "explicame",
                "explícame",
                "detalle",
                "detalles",
                "a detalle",
                "paso a paso",
                "por que",
                "por qué",
                "porque",
                "como funciona",
                "cómo funciona",
                "mas profundo",
                "más profundo",
            )
        )
        images_requested = _user_requested_images(request.message)
        images_line = (
            "El usuario pidió IMÁGENES. Si hay thumbnails en el contexto, descríbelas y sugiere 3-5 opciones (una línea cada una).\n"
            if images_requested
            else ""
        )
        system_content = (
            "Eres la Extensión Cognitiva del usuario.\n"
            + user_name_line
            + images_line
            + (
                "El usuario pidió explicación: puedes responder con más detalle, pero sé directo (máximo 10-14 líneas).\n"
                "Usa: 1 frase + 3-6 viñetas.\n"
                if wants_detail
                else "Responde corto por defecto: máximo 2-4 líneas, o 3 viñetas cortas.\n"
            )
            + "No escribas artículos largos. No repitas la pregunta.\n\n"
            + "FORMATO DE RESPUESTA (OBLIGATORIO):\n"
            + "- Devuelve ÚNICAMENTE texto plano.\n"
            + "- NO incluyas JSON, XML, Markdown ni bloques de código.\n"
        )
        if context_prompt:
            system_content += "\n\n" + context_prompt
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": request.message},
        ]
        ai_text = await chat_with_ai(messages=messages, user=user_id, fast_reasoning=True, stream=False)
        structured = _sanitize_structured_data({"response": ai_text, "tasks": [], "plan": [], "actions": [], "is_stream": False})
        
        # Guardar progreso
        asyncio.create_task(save_user_progress(user_id, request.message, structured))
        
        # Guardar en cache semántico para futuras consultas similares
        if not structured.get("is_stream"):
            await embeddings_service.add_to_semantic_cache(request.message, structured["response"])
        
        context_info = get_context_info(user_id)

        message_id = f"msg_{datetime.utcnow().timestamp()}"
        return ChatResponse(
            success=True,
            response=structured["response"],
            user_id=user_id,
            timestamp=datetime.utcnow().isoformat(),
            context={
                "usage_percent": round(context_info.get("usage", 0) * 100, 1),
                "needs_refresh": False,
                "auto_refreshed": False,
                "session_id": request.session_id,
                "tasks_count": len(user_context.get("tasks_today", []))
            },
            message_id=message_id,
            actions=[
                {"type": "tasks", "data": structured["tasks"]},
                {"type": "plan", "data": structured["plan"]}
            ],
            sources=sources if sources else None,
            rich_response=_build_rich_response(
                text=str(structured.get("response") or ""),
                memory_id=message_id,
                sources=sources if sources else None,
            ),
        )
        
    except RuntimeError as e:
        if "GROQ_API_KEY" in str(e):
            raise HTTPException(status_code=503, detail="llm_unavailable_missing_groq_api_key")
        raise
    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()
        logger.error(
            f"unified_chat_message_json FAILED: {type(e).__name__}: {e}\n{tb_str}",
            extra={
                "user_id": str(user.get("user_id") if isinstance(user, dict) else ""),
                "error_type": type(e).__name__,
                "error": str(e),
            }
        )
        detail_error = str(e) if _debug_enabled() else "internal_error"
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": detail_error,
                "error_code": "CHAT_ERROR",
                "timestamp": datetime.utcnow().isoformat()
            }
        )

@router.post("/context/refresh/{user_id}")
async def refresh_user_context(user_id: str, user: dict = Depends(get_current_user)):
    """Forzar refresh del contexto del usuario"""
    from services.groq_ai_service import user_contexts
    token_user_id = str(user.get("user_id") or user.get("id") or "")
    if token_user_id != str(user_id):
        raise HTTPException(status_code=403, detail="forbidden_user_id_mismatch")
    if user_id in user_contexts:
        del user_contexts[user_id]
    return {
        "success": True,
        "user_id": user_id,
        "timestamp": datetime.utcnow().isoformat()
    }

@router.get("/health")
async def chat_health():
    """Health check del servicio de chat"""
    import os
    return {
        "status": "healthy",
        "service": "unified-chat",
        "version": "5.0",
        "features": ["text", "voice", "websocket", "context_monitoring"],
        "git_sha": os.getenv("GIT_SHA", "unknown"),
        "timestamp": datetime.utcnow().isoformat()
    }

@router.get("/info")
async def chat_info():
    """Información del servidor de chat para frontend"""
    return {
        "service": "unified-chat",
        "version": "5.0",
        "model": "auto",
        "provider": "Groq",
        "features": {
            "text_chat": True,
            "voice_chat": True,
            "websocket": True,
            "context_monitoring": True,
            "auto_context_refresh": True
        },
        "limits": {
            "max_context_tokens": 32000,
            "context_threshold_percent": 85,
            "max_audio_size_mb": 10
        },
    }


@router.websocket("/ws/{user_id}")
async def unified_chat_websocket(websocket: WebSocket, user_id: str):
    """WebSocket para chat en tiempo real con monitoreo de contexto"""

    await websocket.accept()
    logger.info(f"WebSocket accepted for user_id={user_id}")

    try:
        logger.info(f"Starting auth for user_id={user_id}")
        try:
            token_user_id = await _ws_auth_user_id(websocket)
        except Exception as auth_error:
            import traceback
            logger.error(
                f"WebSocket AUTH FAILED for user_id={user_id}: {type(auth_error).__name__}: {auth_error}\n{traceback.format_exc()}"
            )
            debug = {"stack": str(auth_error)} if _debug_enabled() else None
            await _ws_send_json(
                websocket,
                {
                    "type": "error",
                    "message": "auth_failed",
                    **({"debug": debug} if debug else {}),
                },
            )
            await websocket.close(code=1008)
            return
        logger.info(f"Auth successful: token_user_id={token_user_id}, path_user_id={user_id}")
        
        if str(token_user_id) != str(user_id):
            logger.warning(f"User ID mismatch: token={token_user_id}, path={user_id}")
            await _ws_send_json(
                websocket,
                {
                    "type": "error",
                    "message": "forbidden_user_id_mismatch",
                    "debug": {"token_user_id": str(token_user_id), "path_user_id": str(user_id)},
                },
            )
            await websocket.close(code=1008)
            return

        max_text_len = 8000
        logger.info(f"WebSocket connected successfully for user_id={user_id}, waiting for messages")

        # Iniciar heartbeat task
        heartbeat_task = asyncio.create_task(_ws_heartbeat(websocket))

        while True:
            try:
                logger.debug(f"Waiting for message from user_id={user_id}")
                data = await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnect user_id={user_id}")
                break
            except Exception as e:
                logger.error(f"WebSocket receive error user_id={user_id}: {e}")
                break

            logger.info(f"Received message from user_id={user_id}, len={len(data) if data else 0}")
            
            # Manejar pong del cliente si lo envía
            if data == "pong" or (data.startswith("{") and '"type":"pong"' in data):
                logger.debug(f"Received pong from {user_id}")
                continue
            if data is not None and len(data) > max_text_len:
                debug = {"max_len": max_text_len, "len": len(data)} if _debug_enabled() else None
                await _ws_send_json(
                    websocket,
                    {
                        "type": "error",
                        "message": "payload_too_large",
                        **({"debug": debug} if debug else {}),
                    },
                )
                try:
                    await websocket.close(code=1009)
                except Exception:
                    pass
                break

            try:
                message_data = json.loads(data)
            except Exception as e:
                logger.warning(f"WebSocket invalid JSON user_id={user_id}: {e}")
                debug = {"stack": str(e)} if _debug_enabled() else None
                await _ws_send_json(
                    websocket,
                    {
                        "type": "error",
                        "message": "invalid_json",
                        **({"debug": debug} if debug else {}),
                    },
                )
                continue

            from services.ddg_search_service import ddg_search_service
            from services.tavily_search_service import tavily_search_service
            from services.serper_search_service import serper_search_service
            from services.hub_memory_service import hub_memory_service
            from services.browser_mcp_service import browser_mcp_service
            from services.youtube_transcript_service import youtube_transcript_service
            start_ts = datetime.utcnow()

            user_message = str(message_data.get("message", "") or "")
            request_id = _new_request_id()
            logger.info(
                f"chat_ws_start request_id={request_id} user_id={user_id} message_len={len(user_message or '')} images={_user_requested_images(user_message)} web_search={_should_web_search(user_id=user_id, message=user_message)}"
            )
            messages = [{"role": "user", "content": user_message}]
            should_refresh_context(user_id, messages)

            yt_video_id = youtube_transcript_service.extract_video_id(user_message)
            yt_source = None
            web_source = None
            user_context = await get_user_context_for_chat(user_id)

            ddg_sources = []
            if _should_web_search(user_id=user_id, message=user_message):
                await _ws_send_status(websocket, "Buscando en la web...")
                ddg_meta = {"status": "skipped"}
                ws_t0 = time.monotonic()

                include_images = _should_include_images_in_search(user_message)

                # 1) Tavily (primario) con rotación por user_id
                tavily_sources: List[Dict[str, str]] = []
                tavily_meta: Dict[str, Any] = {"status": "disabled"}
                if tavily_search_service.enabled():
                    try:
                        tavily_sources, tavily_meta = await tavily_search_service.search_with_meta(
                            query=user_message.strip(),
                            user_id=str(user_id),
                            include_images=include_images,
                        )
                    except Exception:
                        tavily_sources = []
                        tavily_meta = {"status": "failed"}

                if tavily_sources:
                    ddg_sources = list(tavily_sources)
                    logger.info(
                        f"web_search_provider request_id={request_id} user_id={user_id} provider=tavily meta={_safe_meta(tavily_meta)} results={len(ddg_sources)} duration_ms={int((time.monotonic()-ws_t0)*1000)}"
                    )
                    user_context = dict(user_context)
                    user_context["web_search_results"] = list(ddg_sources or [])[:5]
                    if include_images:
                        user_context["web_search_images_requested"] = True
                else:
                    # 2) Serper (secundario) con rotación por user_id
                    serper_meta: Dict[str, Any] = {"status": "disabled"}
                    if serper_search_service.enabled():
                        try:
                            ddg_sources, serper_meta = await serper_search_service.search_with_meta(
                                query=user_message.strip(),
                                user_id=str(user_id),
                                include_images=include_images,
                            )
                        except Exception:
                            ddg_sources = []
                            serper_meta = {"status": "failed"}

                    if ddg_sources:
                        logger.info(
                            f"web_search_provider request_id={request_id} user_id={user_id} provider=serper meta={_safe_meta(serper_meta)} results={len(ddg_sources)} duration_ms={int((time.monotonic()-ws_t0)*1000)}"
                        )

                    # 3) DDG fallback
                    if not ddg_sources:
                        try:
                            ddg_sources, ddg_meta = await ddg_search_service.search_with_meta(user_message.strip())
                        except Exception:
                            ddg_sources = []
                            ddg_meta = {"status": "failed"}

                        logger.info(
                            f"web_search_provider request_id={request_id} user_id={user_id} provider=ddg meta={_safe_meta(ddg_meta)} results={len(ddg_sources)} duration_ms={int((time.monotonic()-ws_t0)*1000)}"
                        )

                if ddg_sources:
                    user_context = dict(user_context)
                    user_context["web_search_results"] = list(ddg_sources or [])[:5]
                    if include_images:
                        user_context["web_search_images_requested"] = True
                else:
                    # no enviar error crudo al cliente; solo un estado
                    status_val = None
                    if isinstance(tavily_meta, dict) and tavily_meta.get("status") not in (None, "ok"):
                        status_val = tavily_meta.get("status")
                    if status_val is None and isinstance(serper_meta, dict) and serper_meta.get("status") not in (None, "ok"):
                        status_val = serper_meta.get("status")
                    if status_val is None and isinstance(ddg_meta, dict) and ddg_meta.get("status") not in (None, "ok", "cache_hit"):
                        status_val = ddg_meta.get("status")
                    if status_val is not None:
                        user_context = dict(user_context)
                        user_context["web_search_status"] = str(status_val or "failed")
            if yt_video_id:
                await _ws_send_status(websocket, "Leyendo transcripción de YouTube...")
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

            if browser_mcp_service.enabled() and not yt_video_id:
                url = browser_mcp_service.extract_first_url(user_message)
                if url:
                    await _ws_send_status(websocket, "Leyendo página web...")
                    extracted = await browser_mcp_service.fetch_page_extract(url=url)
                    if isinstance(extracted, dict) and str(extracted.get("text") or "").strip():
                        user_context = dict(user_context)
                        user_context["web_extract"] = str(extracted.get("text") or "")
                        web_source = browser_mcp_service.build_source(
                            url=str(extracted.get("url") or url),
                            title=str(extracted.get("title") or ""),
                            snippet=str(extracted.get("text") or "")[:400],
                        )

            # Media primero: mandar galería (imágenes/videos) antes de streamear texto
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

                max_sources_preview = 5 if _should_include_images_in_search(user_message) else 3
                if _should_include_images_in_search(user_message):
                    prioritized_preview: List[Dict[str, Any]] = []
                    remainder_preview: List[Dict[str, Any]] = []
                    for s in list(combined_preview):
                        if not isinstance(s, dict):
                            continue
                        if str(s.get("image") or "").strip():
                            prioritized_preview.append(s)
                        else:
                            remainder_preview.append(s)
                    preview_sources = (prioritized_preview + remainder_preview)[:max_sources_preview]
                else:
                    preview_sources = list(combined_preview)[:max_sources_preview]

                rich_preview = _build_rich_response(text="", memory_id=None, sources=preview_sources)
                if rich_preview is not None:
                    await _ws_send_json(
                        websocket,
                        {
                            "type": "rich",
                            "sources": preview_sources,
                            "rich_response": rich_preview.model_dump(),
                        },
                    )
            except Exception as e:
                logger.warning(f"ws_rich_preview_failed user_id={user_id}: {e}")

            # 1) Streaming Groq -> type=token
            try:
                await _ws_send_status(websocket, "Generando respuesta...")
                ai_result = await get_ai_response_with_streaming(
                    user_id,
                    user_message,
                    user_context,
                    websocket,
                )
            except Exception as e:
                logger.exception(f"WebSocket streaming error user_id={user_id}: {e}")
                debug = {"stack": str(e)} if _debug_enabled() else None
                await _ws_send_json(
                    websocket,
                    {
                        "type": "error",
                        "message": "llm_error",
                        **({"debug": debug} if debug else {}),
                    },
                )
                continue

            text = str(ai_result.get("text") or "")
            logger.info(
                f"chat_ws_done request_id={request_id} user_id={user_id} latency_ms={int((datetime.utcnow()-start_ts).total_seconds()*1000)} response_len={len(text or '')} sources={len(list(ddg_sources or []))}"
            )

            # 2) MCP-like búsqueda (DuckDuckGo) -> sources
            # MVP: usar el mismo mensaje como query; si quieres heurística, se ajusta aquí.
            query = user_message.strip()
            sources = []
            if isinstance(ddg_sources, list) and ddg_sources:
                sources = list(ddg_sources)
            combined_sources = []
            if yt_source:
                combined_sources.append(yt_source)
            if web_source:
                combined_sources.append(web_source)
            combined_sources.extend(list(sources or []))
            max_sources = 5 if _should_include_images_in_search(user_message) else 3
            if _should_include_images_in_search(user_message):
                prioritized = []
                remainder = []
                for s in list(combined_sources):
                    if not isinstance(s, dict):
                        continue
                    if str(s.get("image") or "").strip():
                        prioritized.append(s)
                    else:
                        remainder.append(s)
                sources = (prioritized + remainder)[:max_sources]
            else:
                sources = list(combined_sources)[:max_sources]

            # 3) Guardar memoria en Redis -> memory_id
            latency_ms = int((datetime.utcnow() - start_ts).total_seconds() * 1000)
            debug = {
                "latency_ms": latency_ms,
                "query": query,
            }
            memory_id = str(uuid.uuid4())

            async def _persist_memory() -> None:
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

            asyncio.create_task(_persist_memory())

            # 4) Mensaje final (contrato estricto: type=complete)
            rich_response = _build_rich_response(text=text, memory_id=memory_id, sources=sources)
            await _ws_send_json(
                websocket,
                {
                    "type": "complete",
                    "text": text,
                    "memory_id": memory_id,
                    "sources": sources,
                    "rich_response": rich_response.model_dump() if rich_response else None,
                    "debug": debug,
                },
            )

    except json.JSONDecodeError as e:
        logger.warning(f"WebSocket JSON decode error for user_id={user_id}: {e}")
        try:
            debug = {"stack": str(e)} if _debug_enabled() else None
            await _ws_send_json(
                websocket,
                {
                    "type": "error",
                    "message": "invalid_json",
                    **({"debug": debug} if debug else {}),
                },
            )
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
    except Exception as e:
        import traceback
        tb_str = traceback.format_exc()
        logger.error(
            f"WebSocket ERROR for user_id={user_id}: {type(e).__name__}: {e}\n{tb_str}"
        )
        try:
            debug = {"stack": str(e)} if _debug_enabled() else None
            await _ws_send_json(
                websocket,
                {
                    "type": "error",
                    "message": "ws_error",
                    **({"debug": debug} if debug else {}),
                },
            )
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        if 'heartbeat_task' in locals():
            heartbeat_task.cancel()
            logger.debug(f"Heartbeat task cancelled for user_id={user_id}")


@router.websocket("/voice/ws")
async def voice_stream_ws(websocket: WebSocket):
    """WebSocket para voz en streaming: STT parcial -> LLM -> TTS."""
    await websocket.accept()
    logger.info("Voice WebSocket connection accepted")

    try:
        user_id = await _ws_auth_user_id(websocket)
        logger.info(f"Voice WebSocket authenticated: user_id={user_id}")
    except Exception as e:
        import traceback
        logger.warning(f"Voice WebSocket auth failed: {e}\n{traceback.format_exc()}")
        debug = {"stack": str(e)} if _debug_enabled() else None
        await _ws_send_json(
            websocket,
            {
                "type": "error",
                "message": "auth_failed",
                **({"debug": debug} if debug else {}),
            },
        )
        await websocket.close(code=1008)
        return

    from services.voice_ws_session import VoiceWsConfig, VoiceWsSession

    session = VoiceWsSession(
        send_json=lambda payload: _ws_send_json(websocket, payload),
        chat_with_ai=chat_with_ai,
        now_ts=_ws_now_iso,
        estimate_duration_ms=_estimate_duration_ms_from_bytes,
        tail_bytes_for_pcm16=_tail_bytes_for_pcm16,
        config=VoiceWsConfig(
            max_audio_bytes=_WS_MAX_AUDIO_BYTES,
            partial_interval_ms=_WS_PARTIAL_INTERVAL_MS,
            tail_window_ms=_WS_TAIL_WINDOW_MS,
        ),
    )

    # Loop
    message_count = 0
    binary_bytes_received = 0
    
    # Iniciar heartbeat task
    heartbeat_task = asyncio.create_task(_ws_heartbeat(websocket))
    
    try:
        while True:
            try:
                msg = await websocket.receive()
            except WebSocketDisconnect:
                logger.info(f"Voice WebSocket disconnect: user_id={user_id}")
                break
            except Exception as e:
                logger.error(f"Voice WebSocket receive error user_id={user_id}: {e}")
                break
                
            message_count += 1

            if msg.get("type") == "websocket.disconnect":
                logger.info(f"Voice WebSocket disconnect message: user_id={user_id}, messages={message_count}, bytes={binary_bytes_received}")
                break

            if "text" in msg and msg["text"] is not None:
                try:
                    data = json.loads(msg["text"])
                    mtype = data.get("type")
                    logger.debug(f"Voice WS text message: type={mtype}, user_id={user_id}")
                except Exception as e:
                    logger.warning(f"Voice WS invalid JSON: {e}")
                    debug = {"stack": str(e)} if _debug_enabled() else None
                    await _ws_send_json(
                        websocket,
                        {"type": "error", "message": "invalid_json", **({"debug": debug} if debug else {})},
                    )
                    continue

                if mtype == "start":
                    logger.info(f"Voice turn start: user_id={user_id}, format={data.get('format')}, vad={data.get('vad')}")
                    await session.start_turn(data, user_id=user_id)

                elif mtype == "end":
                    logger.info(f"Voice turn end: user_id={user_id}")
                    await session.end_turn(user_id=user_id)

                else:
                    logger.warning(f"Voice WS unknown message type: {mtype}")
                    debug = {"stack": str(mtype)} if _debug_enabled() else None
                    await _ws_send_json(
                        websocket,
                        {"type": "error", "message": "unknown_message_type", **({"debug": debug} if debug else {})},
                    )

            if "bytes" in msg and msg["bytes"] is not None:
                chunk = msg["bytes"]
                if not isinstance(chunk, (bytes, bytearray)):
                    logger.warning(f"Voice WS invalid chunk type: {type(chunk)}")
                    continue
                
                # Auto-start session if audio arrives before explicit start
                if not session.started:
                    logger.info(f"Auto-starting voice session for user={user_id} (audio received before start message)")
                    await session.start_turn({
                        "format": "pcm16",
                        "sample_rate": 16000,
                        "language": "es",
                        "mode": "voice_chat",
                        "vad": True
                    }, user_id=user_id)
                
                chunk_len = len(chunk)
                binary_bytes_received += chunk_len
                
                if message_count % 50 == 1:  # Log cada ~50 chunks para no saturar
                    logger.debug(f"Voice WS binary chunk: {chunk_len} bytes, total={binary_bytes_received}")

                try:
                    await session.add_audio_chunk(bytes(chunk))
                except ValueError as e:
                    logger.error(f"Voice WS audio too large: {e}")
                    await websocket.close(code=1009)
                    return

    except Exception as e:
        logger.exception(f"Voice WebSocket error: user_id={user_id}, messages={message_count}")
        try:
            debug = {"stack": str(e)} if _debug_enabled() else None
            await _ws_send_json(
                websocket,
                {"type": "error", "message": "voice_ws_error", **({"debug": debug} if debug else {})},
            )
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        if 'heartbeat_task' in locals():
            heartbeat_task.cancel()
            logger.debug(f"Voice heartbeat task cancelled for user_id={user_id}")

__all__ = ["router"]