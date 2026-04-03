"""
Chat Context - User context management for chat
Separado de unified_chat_router.py para reducir responsabilidades
"""
import logging
import os
import time
from datetime import datetime, date, timedelta
from typing import Dict, Any, List
from sqlalchemy import select, and_
from models.models import User, SessionItem, RecordingSession
from services.hub_memory_service import hub_memory_service
from utils.auth import get_current_user

logger = logging.getLogger("chat_context")

_USER_CONTEXT_CACHE: Dict[str, Dict[str, Any]] = {}
_USER_CONTEXT_CACHE_TTL_S = float(os.getenv("USER_CONTEXT_CACHE_TTL_S", "20"))


async def _get_user_full_context(user_id: str) -> Dict[str, Any]:
    """Obtiene contexto completo del usuario: tareas + sesiones recientes"""
    context: Dict[str, Any] = {
        "tasks_today": [],
        "tasks_upcoming": [],
        "recent_sessions": [],
        "key_points_recent": [],
        "user_full_name": "",
    }
    
    from database.db_enterprise import get_primary_session
    
    today = date.today()
    end_week = today + timedelta(days=7)
    
    # Query 1: Info del usuario (transacción independiente)
    try:
        db = await get_primary_session()
        async with db:
            stmt_user = select(User).where(User.id == user_id).limit(1)
            result_user = await db.execute(stmt_user)
            user_row = result_user.scalar_one_or_none()
            if user_row is not None:
                context["user_full_name"] = str(getattr(user_row, "full_name", "") or "").strip()
    except Exception as e:
        logger.debug(f"Could not fetch user name: {e}")
    
    # Query 2: Tareas de hoy (transacción independiente)
    try:
        db = await get_primary_session()
        async with db:
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
    except Exception as e:
        logger.debug(f"Could not fetch today's tasks: {e}")
    
    # Query 3: Tareas próximas (transacción independiente)
    try:
        db = await get_primary_session()
        async with db:
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
    except Exception as e:
        logger.debug(f"Could not fetch upcoming tasks: {e}")
    
    # Query 4: Puntos clave recientes (transacción independiente)
    try:
        db = await get_primary_session()
        async with db:
            stmt_points = select(SessionItem).where(
                and_(
                    SessionItem.user_id == user_id,
                    SessionItem.item_type == "key_point",
                    SessionItem.created_at >= datetime.combine(today - timedelta(days=7), datetime.min.time()),
                )
            ).limit(5)
            result = await db.execute(stmt_points)
            points = result.scalars().all()
            context["key_points_recent"] = [
                {"id": p.id, "content": p.content[:100], "created_at": p.created_at.isoformat()}
                for p in points
            ]
    except Exception as e:
        logger.debug(f"Could not fetch key points: {e}")
    
    # Query 5: Sesiones recientes (transacción independiente)
    try:
        db = await get_primary_session()
        async with db:
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
        logger.debug(f"Could not fetch recent sessions: {e}")
    
    return context


async def _get_recent_chat_history(user_id: str, limit: int = 5) -> List[Dict[str, str]]:
    """Recupera los últimos mensajes de la conversación para memoria contextual."""
    try:
        recent_ids = await hub_memory_service.get_recent(user_id=user_id, limit=limit)
        
        history = []
        # Los recibimos del más nuevo al más viejo, los invertimos para el prompt
        for mid in reversed(recent_ids):
            mem = await hub_memory_service.get_memory(memory_id=mid)
            if mem:
                history.append({"role": "user", "content": mem.get("query", "")})
                history.append({"role": "assistant", "content": mem.get("text", "")})
        return history
    except Exception as e:
        logger.warning(f"No se pudo recuperar historial reciente: {e}")
        return []

async def get_user_context_for_chat(user_id: str) -> Dict[str, Any]:
    """Contexto requerido por chat (HTTP y WebSocket) con caching."""
    now = time.monotonic()
    cached = _USER_CONTEXT_CACHE.get(user_id)
    if isinstance(cached, dict):
        ts = cached.get("ts")
        ctx = cached.get("ctx")
        if isinstance(ts, (int, float)) and isinstance(ctx, dict) and (now - float(ts)) <= _USER_CONTEXT_CACHE_TTL_S:
            return dict(ctx)
    
    context = await _get_user_full_context(user_id)
    
    # Inyectar historial reciente (Memoria Contextual)
    context["chat_history"] = await _get_recent_chat_history(user_id)
    
    _USER_CONTEXT_CACHE[user_id] = {"ts": now, "ctx": context}
    return context


def invalidate_user_context(user_id: str):
    """Invalidate cached context for user"""
    _USER_CONTEXT_CACHE.pop(user_id, None)


def build_context_prompt(user_context: Dict[str, Any]) -> str:
    """Construye el prompt de contexto para la IA"""
    prompt_parts = []

    user_full_name = str(user_context.get("user_full_name") or "").strip()
    if user_full_name:
        prompt_parts.append(f"👤 USUARIO: {user_full_name}")
    
    if user_context.get("tasks_today"):
        prompt_parts.append("📋 TAREAS DE HOY:")
        for t in user_context["tasks_today"]:
            prompt_parts.append(f"  - {t.get('title', 'Sin título')}")
    
    if user_context.get("tasks_upcoming"):
        prompt_parts.append("📅 TAREAS PRÓXIMAS:")
        for t in user_context["tasks_upcoming"][:5]:
            due = t.get('due_date', '')
            prompt_parts.append(f"  - {t.get('title', 'Sin título')} (vence: {due})")
    
    if user_context.get("recent_sessions"):
        prompt_parts.append("🎙️ SESIONES RECIENTES:")
        for s in user_context["recent_sessions"][:3]:
            prompt_parts.append(f"  - {s.get('title', 'Sin título')}")
    
    web_search_results = user_context.get("web_search_results")
    if web_search_results:
        prompt_parts.append(
            "🌐 RESULTADOS DE BÚSQUEDA (APIs; úsalos como base, cita fuente cuando puedas):"
        )
        for i, r in enumerate(web_search_results[:5], 1):
            title = r.get("title", "Sin título")
            snippet = str(r.get("snippet") or "")[:900]
            url = str(r.get("url") or "").strip()
            line = f"  [{i}] {title}\n     {snippet}"
            if url:
                line += f"\n     URL: {url}"
            prompt_parts.append(line)
    
    youtube_transcript = user_context.get("youtube_transcript")
    if youtube_transcript:
        prompt_parts.append("📺 TRANSCRIPCIÓN DE YOUTUBE:")
        prompt_parts.append(f"  {youtube_transcript[:500]}")
    
    web_extract = user_context.get("web_extract")
    if web_extract:
        prompt_parts.append("📄 CONTENIDO WEB EXTRAÍDO:")
        prompt_parts.append(f"  {web_extract[:500]}")
    
    # --- MEMORIA CONTEXTUAL (HISTORIAL) ---
    chat_history = user_context.get("chat_history", [])
    if chat_history:
        prompt_parts.append("\n💬 HILO DE CONVERSACIÓN RECIENTE (Para fluidez):")
        for msg in chat_history:
            role = "TÚ" if msg["role"] == "assistant" else "USUARIO"
            prompt_parts.append(f"  {role}: {msg['content'][:300]}")
    
    return "\n".join(prompt_parts)
