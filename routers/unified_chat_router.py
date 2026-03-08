"""
Unified Chat Router Enterprise v5.0
Chat con IA + Voz + Monitoreo de Contexto Automático + Contexto de Tareas y Grabaciones
Diseñado para integración óptima con frontend
"""

from fastapi import APIRouter, WebSocket, UploadFile, File, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from typing import List, Optional, Dict, Any, AsyncGenerator
from pydantic import BaseModel
import json
import logging
from datetime import datetime, date, timedelta

from services.siliconflow_ai_service import chat_with_ai, should_refresh_context, get_context_info
from utils.auth import get_current_user

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

class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    error_code: str
    timestamp: str

# =========================
# PERSISTENCIA DE PROGRESO
# =========================

_user_progress: Dict[str, Dict[str, Any]] = {}

async def save_user_progress(user_id: str, message: str, structured_data: Dict[str, Any]):
    """Guarda el progreso del usuario en memoria (en producción usar Redis/DB)"""
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
    
    # Agregar nuevas tareas
    for task in structured_data.get("tasks", []):
        if task.get("due_date"):
            # Determinar si es para hoy o esta semana
            try:
                from datetime import date
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
    
    # Guardar plan
    if structured_data.get("plan"):
        progress["last_plan"] = structured_data["plan"]
        
    try:
        from database.db_enterprise import get_primary_session
        from models.models import AgendaItem
        async with get_primary_session() as db:
            # Aquí persistimos las tareas detectadas directamente en la DB de NHost
            for task_data in structured_data.get("tasks", []):
                new_task = AgendaItem(
                    user_id=user_id,
                    title=task_data.get("title"),
                    item_type="task",
                    status="pending",
                    priority=task_data.get("priority", "medium"),
                    due_date=datetime.fromisoformat(task_data["due_date"]) if task_data.get("due_date") else None
                )
                db.add(new_task)
            await db.commit()
            logger.info(f"✅ Progress and tasks persisted for user {user_id}")
    except Exception as e:
        logger.error(f"❌ Error persisting user progress to DB: {e}")


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
    
    if user_id not in _user_progress:
        _user_progress[user_id] = {
            "today_tasks": [],
            "week_tasks": [],
            "completed_tasks": [],
            "last_plan": [],
            "last_interaction": None
        }
    
    _user_progress[user_id]["last_plan"] = plan
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
        async with get_primary_session() as db:
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
        pass  # Si falla, retornamos contexto vacío
    
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

async def get_ai_response_with_structured_data(
    user_id: str,
    message: str,
    user_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Obtiene respuesta de IA con datos estructurados (tasks, plan)"""
    from services.siliconflow_ai_service import chat_with_ai
    
    context_prompt = build_context_prompt(user_context)
    
    # Prompt mejorado para respuestas estructuradas
    system_content = """Eres un asistente académico organizado. Cuando respondas, SIEMPRE incluye:

1. **tasks**: Lista de tareas mencionadas o creadas (cada tarea con: title, due_date si se menciona, priority)
2. **plan**: Plan de estudio o acción para el usuario (array de pasos concretos)
3. **response**: Tu respuesta en texto para el usuario

Formato JSON obligatorio:
{
  "tasks": [{"title": "...", "due_date": "YYYY-MM-DD o null", "priority": "high/medium/low"}],
  "plan": [{"step": "...", "duration": "minutos o null"}],
  "response": "Tu respuesta en texto"
}

Si no hay tareas, usa array vacío: "tasks": []
Si no hay plan, usa array vacío: "plan": []"""

    if context_prompt:
        system_content += "\n\n" + context_prompt
    
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": message}
    ]
    
    # Obtener respuesta de IA
    ai_response = await chat_with_ai(
        messages=messages,
        user=user_id,
        fast_reasoning=True
    )
    
    # Intentar parsear como JSON estructurado
    structured_data = {
        "tasks": [],
        "plan": [],
        "response": ai_response,
        "is_stream": False
    }
    
    # Si ai_response es un generador (streaming), retornamos un objeto especial
    if hasattr(ai_response, "__aiter__"):
        return {"response": ai_response, "is_stream": True}
    
    # Buscar JSON en la respuesta
    import re
    json_match = re.search(r'\{[\s\S]*\}', ai_response)
    if json_match:
        try:
            import json
            parsed = json.loads(json_match.group())
            if isinstance(parsed, dict):
                structured_data["tasks"] = parsed.get("tasks", [])
                structured_data["plan"] = parsed.get("plan", [])
                structured_data["response"] = parsed.get("response", ai_response)
        except:
            pass  # Si falla el parseo, usar respuesta original
    
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
        
        if stream:
            # Endpoint optimizado para streaming real
            async def response_generator():
                full_response = []
                # Obtener el generador de streaming primero
                stream_gen = await chat_with_ai(
                    messages=[{"role": "user", "content": message}],
                    user=user_id,
                    stream=True
                )
                # Ahora iterar sobre el generador
                async for chunk in stream_gen:
                    full_response.append(chunk)
                    yield f"data: {json.dumps({'content': chunk})}\n\n"
                
                # Al final, persistir si es posible (en background)
                asyncio.create_task(embeddings_service.add_to_semantic_cache(message, "".join(full_response)))
            
            return StreamingResponse(response_generator(), media_type="text/event-stream")

        # Obtener respuesta estructurada (no stream)
        structured = await get_ai_response_with_structured_data(user_id, message, user_context)
        
        # Guardar progreso del usuario
        await save_user_progress(user_id, message, structured)
        
        # Guardar en cache semántico para futuras consultas similares
        if not structured.get("is_stream"):
            await embeddings_service.add_to_semantic_cache(message, structured["response"])
        
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
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": str(e),
                "error_code": "CHAT_ERROR",
                "timestamp": datetime.utcnow().isoformat()
            }
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
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": str(e),
                "error_code": "CHAT_ERROR",
                "timestamp": datetime.utcnow().isoformat()
            }
        )

@router.post("/voice/message", response_model=VoiceChatResponse)
async def chat_with_voice(
    audio: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Chat por voz - STT → Qwen3 → TTS"""
    
    try:
        audio_bytes = await audio.read()
        
        from services.siliconflow_ai_service import transcribe_audio, text_to_speech
        
        text = await transcribe_audio(audio_bytes)
        
        response = await chat_with_ai(
            messages=[{"role": "user", "content": text}],
            user=user["user_id"]
        )
        
        audio_response = await text_to_speech(response)
        
        return VoiceChatResponse(
            success=True,
            transcribed=text,
            response=response,
            audio=audio_response,
            user_id=user["user_id"],
            timestamp=datetime.utcnow().isoformat(),
            message_id=f"voice_{datetime.utcnow().timestamp()}"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": str(e),
                "error_code": "VOICE_CHAT_ERROR",
                "timestamp": datetime.utcnow().isoformat()
            }
        )

@router.get("/context/{user_id}", response_model=ContextResponse)
async def get_user_context(user_id: str):
    """Obtener información de contexto del usuario"""
    info = get_context_info(user_id)
    return ContextResponse(
        user_id=user_id,
        usage_percent=round(info.get("usage", 0) * 100, 1),
        messages_count=info.get("messages_count", 0),
        last_check=info.get("last_check").isoformat() if info.get("last_check") else None
    )

@router.post("/context/refresh/{user_id}")
async def refresh_user_context(user_id: str):
    """Forzar refresh del contexto del usuario"""
    from services.siliconflow_ai_service import user_contexts
    if user_id in user_contexts:
        del user_contexts[user_id]
    return {
        "success": True, 
        "message": "Contexto refrescado", 
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
        "model": "Qwen/Qwen3-VL-32B-Instruct",
        "provider": "SiliconFlow",
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
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            messages = [{"role": "user", "content": message_data.get("message", "")}]
            needs_refresh = should_refresh_context(user_id, messages)
            
            response = await chat_with_ai(
                messages=messages,
                user=user_id,
                fast_reasoning=message_data.get("fast_reasoning", True)
            )
            
            await websocket.send_text(json.dumps({
                "success": True,
                "response": response,
                "message_id": f"ws_{datetime.utcnow().timestamp()}",
                "context": {
                    "needs_refresh": needs_refresh,
                    "auto_refreshed": needs_refresh
                },
                "timestamp": datetime.utcnow().isoformat()
            }))
            
    except json.JSONDecodeError:
        await websocket.send_text(json.dumps({
            "success": False,
            "error": "Invalid JSON",
            "error_code": "INVALID_JSON",
            "timestamp": datetime.utcnow().isoformat()
        }))
        await websocket.close()
    except Exception as e:
        await websocket.send_text(json.dumps({
            "success": False,
            "error": str(e),
            "error_code": "WS_ERROR",
            "timestamp": datetime.utcnow().isoformat()
        }))
        await websocket.close()

__all__ = ["router"]