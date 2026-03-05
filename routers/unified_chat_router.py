"""
Unified Chat Router Enterprise v5.0
Chat con IA + Voz + Monitoreo de Contexto Automático + Contexto de Tareas y Grabaciones
Diseñado para integración óptima con frontend
"""

from fastapi import APIRouter, WebSocket, UploadFile, File, Depends, HTTPException, Request
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import json
from datetime import datetime, date, timedelta

from services.siliconflow_ai_service import chat_with_ai, should_refresh_context, get_context_info
from utils.auth import get_current_user

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

@router.post("/message", response_model=ChatResponse)
async def unified_chat_message(
    message: str,
    files: Optional[List[UploadFile]] = File(None),
    user: dict = Depends(get_current_user),
):
    """Chat con IA - incluye contexto de tareas y grabaciones"""
    
    try:
        user_id = user["user_id"]
        
        # Obtener contexto del usuario
        user_context = await get_user_context_for_chat(user_id)
        context_prompt = build_context_prompt(user_context)
        
        # Construir mensajes con contexto
        system_content = "Eres un asistente académico útil. Cuando el usuario pregunte sobre tareas, fechas límite, o temas de clases, usa la información de contexto proporcionada. Si detectas que el usuario necesita crear una tarea, sugiere crearla."
        if context_prompt:
            system_content += "\n\n" + context_prompt
        
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": message}
        ]
        
        context_info = get_context_info(user_id)
        needs_refresh = should_refresh_context(user_id, messages)
        
        response = await chat_with_ai(
            messages=messages,
            user=user_id,
            fast_reasoning=True
        )
        
        return ChatResponse(
            success=True,
            response=response,
            user_id=user_id,
            timestamp=datetime.utcnow().isoformat(),
            context={
                "usage_percent": round(context_info.get("usage", 0) * 100, 1),
                "needs_refresh": needs_refresh,
                "auto_refreshed": needs_refresh,
                "tasks_count": len(user_context.get("tasks_today", [])),
                "upcoming_tasks_count": len(user_context.get("tasks_upcoming", []))
            },
            message_id=f"msg_{datetime.utcnow().timestamp()}"
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
    """Chat con IA - versión JSON body con contexto"""
    
    try:
        user_id = user["user_id"]
        
        # Obtener contexto del usuario
        user_context = await get_user_context_for_chat(user_id)
        context_prompt = build_context_prompt(user_context)
        
        system_content = "Eres un asistente académico útil. Cuando el usuario pregunte sobre tareas, fechas límite, o temas de clases, usa la información de contexto proporcionada."
        if context_prompt:
            system_content += "\n\n" + context_prompt
        
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": request.message}
        ]
        
        context_info = get_context_info(user_id)
        needs_refresh = should_refresh_context(user_id, messages)
        
        response = await chat_with_ai(
            messages=messages,
            user=user_id,
            fast_reasoning=True
        )
        
        return ChatResponse(
            success=True,
            response=response,
            user_id=user_id,
            timestamp=datetime.utcnow().isoformat(),
            context={
                "usage_percent": round(context_info.get("usage", 0) * 100, 1),
                "needs_refresh": needs_refresh,
                "auto_refreshed": needs_refresh,
                "session_id": request.session_id,
                "tasks_count": len(user_context.get("tasks_today", []))
            },
            message_id=f"msg_{datetime.utcnow().timestamp()}"
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