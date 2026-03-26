"""
Chat Progress - User progress and task management for chat
Separado de unified_chat_router.py para reducir responsabilidades
"""
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List

from models.models import SessionItem, RecordingSession, RecordingSessionType

logger = logging.getLogger("chat_progress")

_user_progress: Dict[str, Dict[str, Any]] = {}


def _sanitize_structured_data(structured_data: Any) -> Dict[str, Any]:
    """Sanitiza y normaliza datos estructurados de la IA"""
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
    
    is_stream = bool(structured_data.get("is_stream", False))
    return {"tasks": tasks, "plan": plan, "response": response, "is_stream": is_stream}


async def save_user_progress(user_id: str, message: str, structured_data: Dict[str, Any]):
    """Guarda el progreso del usuario en memoria y persiste en DB"""
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
    await _persist_tasks_to_db(user_id, structured_data)
    
    # Ejecutar acciones automáticas
    await _execute_auto_actions(user_id, structured_data)


async def _persist_tasks_to_db(user_id: str, structured_data: Dict[str, Any]):
    """Persist tasks to database"""
    try:
        from database.db_enterprise import get_primary_session
        from sqlalchemy import select, and_
        
        db = await get_primary_session()
        async with db:
            # Asegurar que existe una sesión activa para este usuario
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
                    except (ValueError, TypeError):
                        pass

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


async def _execute_auto_actions(user_id: str, structured_data: Dict[str, Any]):
    """Execute automatic actions from AI response"""
    if not structured_data.get("actions"):
        return
        
    for action in structured_data["actions"]:
        action_type = action.get("type")
        action_data = action.get("data")
        
        if action_type == "schedule_class":
            await _schedule_class_action(user_id, action_data)
        elif action_type == "generate_document":
            await _generate_document_action(user_id, action_data)


async def _schedule_class_action(user_id: str, action_data: Dict[str, Any]):
    """Schedule a class/event from AI action"""
    logger.info(f"🤖 AI ACCIÓN AUTOMÁTICA: Agendando clase/evento - {action_data}")
    try:
        from database.db_enterprise import get_primary_session
        from sqlalchemy import select, and_
        
        db = await get_primary_session()
        async with db:
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
                except (ValueError, TypeError):
                    pass

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


async def _generate_document_action(user_id: str, action_data: Dict[str, Any]):
    """Generate document from AI action"""
    logger.info(f"🤖 AI ACCIÓN AUTOMÁTICA: Preparando documento - {action_data}")
    try:
        from services.document_service import create_document_from_user_message
        import asyncio
        asyncio.create_task(create_document_from_user_message(
            user_message=action_data.get("content", ""),
            user_id=user_id,
            doc_type=action_data.get("format", "pdf")
        ))
        logger.info(f"✅ Ejecución silenciosa iniciada: generate_document")
    except Exception as e:
        logger.error(f"❌ Fallo al iniciar ejecución silenciosa: {e}")


def get_user_progress(user_id: str) -> Dict[str, Any]:
    """Get user progress from memory"""
    if user_id not in _user_progress:
        return {
            "today_tasks": [],
            "week_tasks": [],
            "completed_tasks": [],
            "last_plan": [],
            "last_interaction": None
        }
    return _user_progress[user_id]


def complete_task(user_id: str, task_id: str) -> bool:
    """Mark task as completed"""
    if user_id not in _user_progress:
        return False
    
    progress = _user_progress[user_id]
    
    for task_list in ["today_tasks", "week_tasks"]:
        for i, task in enumerate(progress.get(task_list, [])):
            if task.get("id") == task_id:
                progress["completed_tasks"].append({
                    **task,
                    "completed_at": datetime.utcnow().isoformat()
                })
                progress[task_list].pop(i)
                return True
    return False


def save_user_plan(user_id: str, plan: List[Dict[str, Any]]):
    """Save user study plan"""
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
