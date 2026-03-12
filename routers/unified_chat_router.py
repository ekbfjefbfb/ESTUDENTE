"""
Unified Chat Router Enterprise v5.0
Chat con IA + Voz + Monitoreo de Contexto Automático + Contexto de Tareas y Grabaciones
Diseñado para integración óptima con frontend
"""

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File, Depends, HTTPException, Request
from pydantic import BaseModel

from services.groq_ai_service import chat_with_ai, should_refresh_context, get_context_info, sanitize_ai_text
from services.groq_voice_service import transcribe_audio_groq, text_to_speech_groq
from utils.auth import get_current_user, verify_token

_WS_MAX_AUDIO_BYTES = 30 * 1024 * 1024
_WS_PARTIAL_INTERVAL_MS = 400
_WS_TAIL_WINDOW_MS = 4500

logger = logging.getLogger("unified_chat_router")

router = APIRouter(prefix="/unified-chat", tags=["Chat IA"])

# =========================
# SCHEMAS
# =========================

class ChatMessageRequest(BaseModel):
    message: str
    files: Optional[List[str]] = None
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    success: bool
    response: str
    user_id: str
    timestamp: str
    context: Dict[str, Any]
    message_id: Optional[str] = None
    actions: Optional[List[Dict[str, Any]]] = None

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
    payload = await verify_token(token)
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
        await websocket.send_text(json.dumps(payload, ensure_ascii=False))
    except Exception as e:
        logger.error(f"Error sending WebSocket JSON: {e}")
        raise

async def _ws_heartbeat(websocket: WebSocket):
    """Tarea en background para enviar pings y mantener la conexión activa."""
    try:
        while True:
            await asyncio.sleep(60)  # Cada 60 segundos (menos frecuente)
            try:
                # Verificar si la conexión sigue abierta antes de enviar
                if websocket.client_state.CONNECTED:
                    await websocket.send_json({"type": "ping", "ts": _ws_now_iso()})
                    logger.debug("Sent WS heartbeat ping")
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
    
    # Sanitizar el texto para remover caracteres de markdown innecesarios
    response = sanitize_ai_text(response)

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
        from models.models import AgendaItem, AgendaItemType, AgendaItemStatus, AgendaSession
        from sqlalchemy import select, and_
        
        db = await get_primary_session()
        async with db:
            # Asegurar que existe una sesión activa para este usuario para vincular las tareas
            stmt_session = select(AgendaSession).where(
                and_(
                    AgendaSession.user_id == user_id,
                    AgendaSession.class_name == "Chat Asistente"
                )
            ).order_by(AgendaSession.created_at.desc()).limit(1)
            result_session = await db.execute(stmt_session)
            active_session = result_session.scalar_one_or_none()

            if not active_session:
                active_session = AgendaSession(
                    user_id=user_id,
                    class_name="Chat Asistente",
                    status="active",
                    live_transcript="Sesión automática para tareas de chat"
                )
                db.add(active_session)
                await db.flush()

            # Persistir tareas detectadas
            for task_data in structured_data.get("tasks", []):
                title = (task_data.get("title") or "").strip()
                if not title: continue
                
                due_date_val = None
                if task_data.get("due_date"):
                    try:
                        date_str = task_data["due_date"].replace("Z", "").split("T")[0]
                        due_date_val = datetime.fromisoformat(date_str)
                    except (ValueError, TypeError): pass

                new_task = AgendaItem(
                    user_id=user_id,
                    session_id=active_session.id,
                    title=title,
                    content=title,
                    item_type=AgendaItemType.TASK,
                    status=AgendaItemStatus.PENDING,
                    priority=str(task_data.get("priority", "medium")),
                    due_date=due_date_val
                )
                db.add(new_task)
            await db.commit()
            logger.info(f"✅ Progress and tasks persisted for user {user_id}")
    except Exception as e:
        logger.error(f"❌ Error persisting user progress: {e}")


@router.get("/progress")
async def get_user_progress(user=Depends(get_current_user)):
    """Obtener progreso del usuario (hoy, semana, completado, último plan)"""
    user_id = user["user_id"]
    
    if user_id not in _user_progress:
        # Cargar desde DB si está disponible
        user_context = await get_user_context_for_chat(user_id)
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
                if task.get("id") == task_id or task.get("title"):
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
    user_context = await get_user_context_for_chat(user_id)
    
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

async def get_user_context_for_chat(user_id: str) -> Dict[str, Any]:
    """Obtiene contexto completo del usuario: tareas + sesiones recientes"""
    from sqlalchemy import and_, select
    from models.models import AgendaItem, AgendaItemType, AgendaItemStatus, AgendaSession
    
    context = {
        "tasks_today": [],
        "tasks_upcoming": [],
        "recent_sessions": [],
        "key_points": []
    }
    
    try:
        from database.db_enterprise import get_primary_session
        db = await get_primary_session()
        async with db:
            today = date.today()
            end_week = today + timedelta(days=7)
            
            # Tareas de hoy
            stmt_tasks_today = select(AgendaItem).where(
                and_(
                    AgendaItem.user_id == user_id,
                    AgendaItem.item_type == AgendaItemType.TASK,
                    AgendaItem.due_date >= datetime.combine(today, datetime.min.time()),
                    AgendaItem.status != AgendaItemStatus.DONE
                )
            ).limit(10)
            result = await db.execute(stmt_tasks_today)
            tasks_today = result.scalars().all()
            context["tasks_today"] = [
                {"id": t.id, "title": t.title, "due_date": t.due_date.isoformat() if t.due_date else None}
                for t in tasks_today
            ]
            
            # Tareas próximas (próxima semana)
            stmt_tasks_upcoming = select(AgendaItem).where(
                and_(
                    AgendaItem.user_id == user_id,
                    AgendaItem.item_type == AgendaItemType.TASK,
                    AgendaItem.due_date >= datetime.combine(today, datetime.min.time()),
                    AgendaItem.due_date < datetime.combine(end_week, datetime.max.time()),
                    AgendaItem.status != AgendaItemStatus.DONE
                )
            ).order_by(AgendaItem.due_date).limit(10)
            result = await db.execute(stmt_tasks_upcoming)
            tasks_upcoming = result.scalars().all()
            context["tasks_upcoming"] = [
                {"id": t.id, "title": t.title, "due_date": t.due_date.isoformat() if t.due_date else None}
                for t in tasks_upcoming
            ]
            
            # Puntos clave recientes
            stmt_points = select(AgendaItem).where(
                and_(
                    AgendaItem.user_id == user_id,
                    AgendaItem.item_type == AgendaItemType.KEY_POINT,
                    AgendaItem.created_at >= datetime.combine(today - timedelta(days=7), datetime.min.time())
                )
            ).limit(5)
            result = await db.execute(stmt_points)
            key_points = result.scalars().all()
            context["key_points"] = [
                {"id": p.id, "title": p.title, "content": p.content[:200] if p.content else ""}
                for p in key_points
            ]
            
            # Sesiones recientes con transcripción
            stmt_sessions = select(AgendaSession).where(
                and_(
                    AgendaSession.user_id == user_id,
                    AgendaSession.live_transcript.isnot(None),
                    AgendaSession.live_transcript != ""
                )
            ).order_by(AgendaSession.created_at.desc()).limit(3)
            result = await db.execute(stmt_sessions)
            sessions = result.scalars().all()
            context["recent_sessions"] = [
                {
                    "id": s.id,
                    "class_name": s.class_name,
                    "topic": s.topic,
                    "transcript_preview": (s.live_transcript or "")[:500]
                }
                for s in sessions
            ]
    except Exception as e:
        logger.error(f"Error fetching user context: {e}", exc_info=True)
    
    return context


def build_context_prompt(user_context: Dict[str, Any]) -> str:
    """Construye el prompt de contexto para la IA"""
    prompt_parts = []
    
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
    
    if user_context.get("key_points"):
        prompt_parts.append("\n🔑 PUNTOS CLAVE DE CLASES RECIENTES:")
        for p in user_context["key_points"]:
            prompt_parts.append(f"  - {p['title']}: {p['content'][:100]}...")
    
    if user_context.get("recent_sessions"):
        prompt_parts.append("\n🎓 SESIONES RECIENTES:")
        for s in user_context["recent_sessions"]:
            prompt_parts.append(f"  - {s['class_name']}: {s['topic'] or 'Sin tema'}")
    
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
    """
    Streaming REAL: Envía tokens uno por uno al WebSocket
    Al finalizar, parsea y retorna structured data
    """
    from services.groq_ai_service import chat_with_ai, sanitize_ai_text
    
    context_prompt = build_context_prompt(user_context)
    
    # Prompt que fuerza JSON estructurado al final
    system_content = (
        "Eres la Extensión Cognitiva del usuario. Respuestas de 1-3 oraciones máximo.\n\n"
        "ESTILO:\n"
        "• Cero saludos innecesarios. Cero relleno.\n"
        "• Acción inmediata: el usuario habla, tú ejecutas.\n"
        "• Usa emojis relevantes (✅ 📚 ⚠️ 🎯) cuando aporten valor.\n"
        "• Tono: confidente, proactivo, sin disculpas.\n\n"
        "TUS PODERES SOBRE LA BASE DE DATOS:\n"
        "• Crear tareas automáticamente con título, fecha y prioridad.\n"
        "• Agendar clases recurrentes (fines de semana, horarios fijos).\n"
        "• Activar grabaciones de audio automáticamente.\n"
        "• Generar documentos APA7, resúmenes, puntos clave.\n"
        "• Recordar TODO: nombres, fechas, preferencias, historial académico.\n\n"
        "FORMATO DE RESPUESTA (MUY IMPORTANTE):\n"
        'Primero: tu respuesta en texto plano (1-3 oraciones).\n'
        'Luego, al FINAL, incluye este JSON estructurado en una línea separada:\n'
        '{"tasks": [{"title": "...", "due_date": "YYYY-MM-DD", "priority": "high/medium/low"}], '
        '"plan": [{"step": "...", "duration": "..."}], '
        '"actions": [{"type": "schedule_class/generate_document", "data": {...}}], '
        '"response": "tu respuesta aquí"}\n\n'
        "REGLA DE ORO: Ejecuta inmediatamente. Cero confirmaciones.\n"
        "Ejemplo: clase mañana 8am -> '✅ Clase agendada 8am. Grabación ON. 📚 Resumen listo post-clase.'"
    )

    if context_prompt:
        system_content += "\n\n" + context_prompt
    
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": message}
    ]
    
    # Enviar mensaje de inicio de stream
    await _ws_send_json(websocket, {
        "type": "stream_start",
        "message_id": f"stream_{datetime.utcnow().timestamp()}",
        "ts": _ws_now_iso()
    })
    
    # Acumulador de texto completo
    full_text = ""
    buffer = ""
    
    try:
        # Obtener el stream de la IA
        stream_generator = await chat_with_ai(
            messages=messages,
            user=user_id,
            fast_reasoning=True,
            stream=True  # ¡Streaming real!
        )
        
        # Iterar sobre cada chunk del stream
        async for chunk in stream_generator:
            if chunk:
                # Sanitizar el chunk
                sanitized = sanitize_ai_text(chunk)
                if sanitized:
                    full_text += sanitized
                    buffer += sanitized
                    
                    # Enviar tokens en grupos pequeños para eficiencia
                    # pero lo suficientemente rápido para fluidez
                    if len(buffer) >= 3 or "\n" in buffer:  # Enviar cada ~3 chars o en newline
                        await _ws_send_json(websocket, {
                            "type": "token",
                            "content": buffer,
                            "ts": _ws_now_iso()
                        })
                        buffer = ""
        
        # Enviar cualquier contenido restante en el buffer
        if buffer:
            await _ws_send_json(websocket, {
                "type": "token",
                "content": buffer,
                "ts": _ws_now_iso()
            })
        
        # Enviar señal de fin de stream
        await _ws_send_json(websocket, {
            "type": "stream_end",
            "ts": _ws_now_iso()
        })
        
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        await _ws_send_json(websocket, {
            "type": "error",
            "code": "STREAM_ERROR",
            "message": str(e),
            "ts": _ws_now_iso()
        })
        raise
    
    # Parsear structured data del texto completo
    structured_data = {
        "tasks": [],
        "plan": [],
        "actions": [],
        "response": full_text,
        "is_stream": False
    }
    
    # Buscar JSON en la respuesta completa
    try:
        # Buscar patrón JSON al final del texto
        json_match = re.search(r'\{[\s\S]*"tasks"[\s\S]*"plan"[\s\S]*"response"[\s\S]*\}', full_text)
        if json_match:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, dict):
                structured_data["tasks"] = parsed.get("tasks", [])
                structured_data["plan"] = parsed.get("plan", [])
                structured_data["actions"] = parsed.get("actions", [])
                # Usar el response del JSON si existe, sino usar el texto completo
                structured_data["response"] = parsed.get("response", full_text)
    except Exception as e:
        logger.warning(f"Failed to parse structured data from stream: {e}")
        # Si falla el parseo, usar respuesta completa como texto plano
        structured_data["response"] = full_text
    
    return structured_data


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
        
        # Pareto 80/20: Intentar obtener respuesta del cache semántico
        from services.embeddings_service import embeddings_service
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
        
        # Obtener respuesta estructurada (non-streaming para HTTP)
        structured = await get_ai_response_with_structured_data(user_id, message, user_context)
        structured = _sanitize_structured_data(structured)
        
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
                        from models.models import AgendaItem, AgendaItemType, AgendaItemStatus
                        from database.db_enterprise import get_primary_session
                        db = await get_primary_session()
                        async with db:
                            # Mapear datos de la IA a campos de la DB
                            start_time_val = datetime.utcnow()
                            if action_data.get("start_time"):
                                try:
                                    date_str = action_data["start_time"].replace("Z", "").split(".")[0]
                                    start_time_val = datetime.fromisoformat(date_str)
                                except (ValueError, TypeError): pass

                            new_event = AgendaItem(
                                user_id=user_id,
                                session_id=str(uuid.uuid4()), # session_id es obligatorio en DB
                                title=action_data.get("title", "Evento sin título"),
                                item_type=AgendaItemType.EVENT,
                                datetime_start=start_time_val,
                                content=f"Automatización: Grabación={action_data.get('recording', True)}, Recurrente={action_data.get('recurring', 'none')}. Participantes: {', '.join(action_data.get('participants', []))}",
                                status=AgendaItemStatus.PENDING,
                                priority="medium"
                            )
                            db.add(new_event)
                            await db.commit()
                            logger.info(f"✅ Ejecución silenciosa exitosa: {action_type}")
                    except Exception as e:
                        logger.error(f"❌ Fallo en ejecución silenciosa ({action_type}): {e}")

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
            message_id=f"msg_{datetime.utcnow().timestamp()}",
            actions=[
                {"type": "tasks", "data": structured["tasks"]},
                {"type": "plan", "data": structured["plan"]}
            ]
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
    structured = await get_ai_response_with_structured_data(user_id, transcribed, user_context)
    response_text = structured.get("response") if isinstance(structured, dict) else str(structured)

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
        
        # Pareto 80/20: Intentar obtener respuesta del cache semántico
        from services.embeddings_service import embeddings_service
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
        
        # Obtener respuesta estructurada
        structured = await get_ai_response_with_structured_data(user_id, request.message, user_context)
        structured = _sanitize_structured_data(structured)
        
        # Guardar progreso
        await save_user_progress(user_id, request.message, structured)
        
        # Guardar en cache semántico para futuras consultas similares
        if not structured.get("is_stream"):
            await embeddings_service.add_to_semantic_cache(request.message, structured["response"])
        
        context_info = get_context_info(user_id)
        
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
            message_id=f"msg_{datetime.utcnow().timestamp()}",
            actions=[
                {"type": "tasks", "data": structured["tasks"]},
                {"type": "plan", "data": structured["plan"]}
            ]
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
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": str(e),
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
    return {
        "status": "healthy",
        "service": "unified-chat",
        "version": "5.0",
        "features": ["text", "voice", "websocket", "context_monitoring"],
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
        "timestamp": datetime.utcnow().isoformat()
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
            await _ws_send_json(
                websocket,
                {
                    "type": "error",
                    "code": "AUTH_ERROR",
                    "message": f"auth_failed: {str(auth_error)}",
                    "ts": _ws_now_iso(),
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
                    "code": "FORBIDDEN",
                    "message": "user_id_mismatch",
                    "ts": _ws_now_iso(),
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
                await _ws_send_json(
                    websocket,
                    {
                        "type": "error",
                        "code": "PAYLOAD_TOO_LARGE",
                        "message": f"message_too_large_max_{max_text_len}",
                        "ts": _ws_now_iso(),
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
                await _ws_send_json(
                    websocket,
                    {
                        "type": "error",
                        "code": "INVALID_JSON",
                        "message": "invalid_json",
                        "ts": _ws_now_iso(),
                    },
                )
                continue

            messages = [{"role": "user", "content": message_data.get("message", "")}]
            needs_refresh = should_refresh_context(user_id, messages)

            # ========== STREAMING REAL ==========
            # Enviar tokens uno por uno y al final parsear structured data
            try:
                structured = await get_ai_response_with_streaming(
                    user_id, 
                    message_data.get("message", ""), 
                    await get_user_context_for_chat(user_id),
                    websocket
                )
            except Exception as e:
                logger.exception(f"WebSocket streaming error user_id={user_id}: {e}")
                await _ws_send_json(
                    websocket,
                    {
                        "type": "error",
                        "code": "LLM_ERROR",
                        "message": str(e),
                        "ts": _ws_now_iso(),
                    },
                )
                continue

            # Sanitizar respuesta final
            final_response = sanitize_ai_text(structured.get("response", ""))
            
            # Enviar respuesta final completa con metadata
            await _ws_send_json(
                websocket,
                {
                    "type": "complete",
                    "success": True,
                    "response": final_response,
                    "message_id": f"ws_{datetime.utcnow().timestamp()}",
                    "context": {
                        "needs_refresh": needs_refresh,
                        "auto_refreshed": needs_refresh,
                    },
                    "structured": {
                        "tasks": structured.get("tasks", []),
                        "plan": structured.get("plan", []),
                        "actions": structured.get("actions", [])
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
            
            # Guardar progreso en background (no bloquear)
            asyncio.create_task(save_user_progress(user_id, message_data.get("message", ""), structured))

    except json.JSONDecodeError as e:
        logger.warning(f"WebSocket JSON decode error for user_id={user_id}: {e}")
        try:
            await _ws_send_json(
                websocket,
                {
                    "success": False,
                    "error": "Invalid JSON",
                    "error_code": "INVALID_JSON",
                    "timestamp": datetime.utcnow().isoformat(),
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
            await _ws_send_json(
                websocket,
                {
                    "type": "error",
                    "code": "WS_ERROR",
                    "message": "Error interno en el servidor de chat.",
                    "ts": _ws_now_iso(),
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
        await _ws_send_json(
            websocket,
            {
                "type": "error",
                "code": "UNAUTHORIZED",
                "message": f"auth_failed: {str(e)}",
                "ts": _ws_now_iso(),
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
                    await _ws_send_json(
                        websocket,
                        {"type": "error", "code": "INVALID_JSON", "message": "invalid_json", "ts": _ws_now_iso()},
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
                    await _ws_send_json(
                        websocket,
                        {"type": "error", "code": "UNKNOWN_MESSAGE", "message": str(mtype), "ts": _ws_now_iso()},
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
            await _ws_send_json(
                websocket,
                {"type": "error", "code": "WS_ERROR", "message": "Error en la conexión de voz.", "ts": _ws_now_iso()},
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