"""
Chat Context - User context management for chat
Separado de unified_chat_router.py para reducir responsabilidades
"""
import logging
import os
import time
from datetime import datetime, date, timedelta
from typing import Dict, Any

from sqlalchemy import select, and_
from models.models import User, SessionItem, RecordingSession

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
    
    try:
        from database.db_enterprise import get_primary_session
        db = await get_primary_session()
        async with db:
            today = date.today()
            end_week = today + timedelta(days=7)
            
            try:
                stmt_user = select(User).where(User.id == user_id).limit(1)
                result_user = await db.execute(stmt_user)
                user_row = result_user.scalar_one_or_none()
                if user_row is not None:
                    context["user_full_name"] = str(getattr(user_row, "full_name", "") or "").strip()
            except Exception:
                pass

            # Tareas de hoy
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

            # Tareas próximas (próxima semana)
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

            # Puntos clave recientes
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
            
            # Sesiones recientes
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
        if "relation" in msg and "does not exist" in msg:
            logger.warning(f"Database tables not ready: {msg}")
        else:
            logger.error(f"Error al obtener contexto de usuario: {e}")
    
    return context


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
        prompt_parts.append("🌐 RESULTADOS DE BÚSQUEDA:")
        for r in web_search_results[:3]:
            title = r.get("title", "Sin título")
            snippet = r.get("snippet", "")
            prompt_parts.append(f"  - {title}: {snippet[:100]}")
    
    youtube_transcript = user_context.get("youtube_transcript")
    if youtube_transcript:
        prompt_parts.append("📺 TRANSCRIPCIÓN DE YOUTUBE:")
        prompt_parts.append(f"  {youtube_transcript[:500]}")
    
    web_extract = user_context.get("web_extract")
    if web_extract:
        prompt_parts.append("📄 CONTENIDO WEB EXTRAÍDO:")
        prompt_parts.append(f"  {web_extract[:500]}")
    
    return "\n".join(prompt_parts)
