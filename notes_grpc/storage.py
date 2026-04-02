"""
notes_grpc/storage.py — Almacenamiento de notas de clase en Nhost PostgreSQL.

MIGRADO a SQLAlchemy async (PostgreSQL vía Nhost).
Los datos persisten en producción y sobreviven redeploys en Render.

Tablas usadas (ya existen en models/models.py):
  - RecordingSession  → representa una "nota de clase" (transcript + summary)
  - SessionItem       → representa una "tarea" extraída de la nota
"""
from __future__ import annotations

import json
import uuid
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, and_, delete
from sqlalchemy.exc import SQLAlchemyError

from database.db_enterprise import get_primary_session
from models.models import (
    RecordingSession,
    SessionItem,
    RecordingSessionType,
    RecordingSessionStatus,
    SessionItemType,
    SessionItemStatus,
)

logger = logging.getLogger("notes_grpc.storage")

# Constante para distinguir notas del router /api/class-notes
_CLASS_NOTE_TYPE = "class_note"
_CLASS_NOTE_SOURCE = "class_note"  # max 16 chars (String(16) in DB)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class NoteRow:
    id: str
    user_id: str
    title: str
    transcript: str
    summary: str
    key_points: List[str]
    created_at: datetime


@dataclass
class TaskRow:
    id: str
    user_id: str
    note_id: str
    text: str
    due_date: Optional[datetime]
    done: bool
    priority: int


def _session_to_note_row(s: RecordingSession) -> NoteRow:
    """Convierte un RecordingSession al formato NoteRow."""
    # key_points guardado en extracted_state como {"key_points": [...]}
    raw = s.extracted_state or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    key_points = raw.get("key_points", []) if isinstance(raw, dict) else []
    return NoteRow(
        id=s.id,
        user_id=s.user_id,
        title=s.title,
        transcript=s.transcript or "",
        summary=s.summary or "",
        key_points=key_points,
        created_at=s.created_at or _utcnow(),
    )


def _item_to_task_row(it: SessionItem) -> TaskRow:
    """Convierte un SessionItem al formato TaskRow."""
    return TaskRow(
        id=it.id,
        user_id=it.user_id,
        note_id=it.session_id,
        text=it.content or "",
        due_date=it.due_date if isinstance(it.due_date, datetime) else None,
        done=(it.status == "done" or it.status == SessionItemStatus.COMPLETED),
        priority=int(it.priority or 0) if it.priority else 0,
    )


class Storage:
    """
    Capa de persistencia para notas de clase.
    Usa Nhost PostgreSQL vía SQLAlchemy — sin SQLite local.
    """

    def __init__(self, _deprecated_sqlite_path: str = "") -> None:
        # El path SQLite ya no se usa; se mantiene el parámetro
        # para no romper el constructor en class_notes_router.py
        if _deprecated_sqlite_path:
            logger.info(
                "Storage: sqlite_path ignorado. "
                "Usando Nhost PostgreSQL (SQLAlchemy)."
            )

    async def init(self) -> None:
        """No-op: las tablas ya existen en Nhost vía Alembic/models."""
        logger.info("✅ Storage (PostgreSQL) listo — no init necesario.")

    # -------------------------------------------------------------------------
    # CREAR NOTA
    # -------------------------------------------------------------------------

    async def create_note(
        self,
        *,
        user_id: str,
        title: str,
        transcript: str,
        summary: str,
        key_points: List[str],
        tasks: List[Dict[str, Any]],
        created_at: Optional[datetime] = None,
    ) -> Tuple[NoteRow, List[TaskRow]]:
        note_id = str(uuid.uuid4())
        ts = created_at or _utcnow()

        async with await get_primary_session() as db:
            # Crear nota como RecordingSession
            session_obj = RecordingSession(
                id=note_id,
                user_id=user_id,
                title=title,
                transcript=transcript,
                summary=summary,
                extracted_state={"key_points": key_points},
                session_type=_CLASS_NOTE_TYPE,
                status=RecordingSessionStatus.COMPLETED,
                started_at=ts,
                ended_at=ts,
            )
            db.add(session_obj)
            await db.flush()  # necesitamos el id antes de los items

            # Crear tareas como SessionItems
            task_rows: List[TaskRow] = []
            for order, t in enumerate(tasks or []):
                text = str(t.get("text", "")).strip()
                if not text:
                    continue
                due = t.get("due_date")
                due_dt: Optional[datetime] = None
                if isinstance(due, datetime):
                    due_dt = due
                elif isinstance(due, str) and due:
                    try:
                        due_dt = datetime.fromisoformat(due)
                    except Exception:
                        pass

                item_id = str(uuid.uuid4())
                item = SessionItem(
                    id=item_id,
                    session_id=note_id,
                    user_id=user_id,
                    item_type=SessionItemType.TASK,
                    status=SessionItemStatus.SUGGESTED,
                    content=text,
                    due_date=due_dt,
                    priority=str(t.get("priority", 0)),
                    order_index=order,
                    source=_CLASS_NOTE_SOURCE,
                )
                db.add(item)
                task_rows.append(
                    TaskRow(
                        id=item_id,
                        user_id=user_id,
                        note_id=note_id,
                        text=text,
                        due_date=due_dt,
                        done=bool(t.get("done", False)),
                        priority=int(t.get("priority", 0)),
                    )
                )

            await db.commit()
            await db.refresh(session_obj)

        note_row = NoteRow(
            id=note_id,
            user_id=user_id,
            title=title,
            transcript=transcript,
            summary=summary,
            key_points=key_points,
            created_at=ts,
        )
        logger.info(f"📝 Nota creada en Nhost: {note_id} ({len(task_rows)} tareas)")
        return note_row, task_rows

    # -------------------------------------------------------------------------
    # OBTENER NOTA
    # -------------------------------------------------------------------------

    async def get_note(
        self, *, user_id: str, note_id: str
    ) -> Optional[Tuple[NoteRow, List[TaskRow]]]:
        async with await get_primary_session() as db:
            s = await db.get(RecordingSession, note_id)
            if not s or s.user_id != user_id:
                return None

            result = await db.execute(
                select(SessionItem).where(
                    and_(
                        SessionItem.session_id == note_id,
                        SessionItem.user_id == user_id,
                        SessionItem.source == _CLASS_NOTE_SOURCE,
                        SessionItem.item_type == SessionItemType.TASK,
                    )
                ).order_by(SessionItem.order_index)
            )
            items = result.scalars().all()

        return _session_to_note_row(s), [_item_to_task_row(it) for it in items]

    # -------------------------------------------------------------------------
    # LISTAR NOTAS
    # -------------------------------------------------------------------------

    async def list_notes(
        self,
        *,
        user_id: str,
        from_ts: Optional[datetime],
        to_ts: Optional[datetime],
        limit: int,
        offset: int,
    ) -> List[NoteRow]:
        async with await get_primary_session() as db:
            q = select(RecordingSession).where(
                and_(
                    RecordingSession.user_id == user_id,
                    RecordingSession.session_type == _CLASS_NOTE_TYPE,
                )
            )
            if from_ts:
                q = q.where(RecordingSession.created_at >= from_ts)
            if to_ts:
                q = q.where(RecordingSession.created_at <= to_ts)

            q = q.order_by(RecordingSession.created_at.desc()).offset(offset).limit(limit)
            result = await db.execute(q)
            sessions = result.scalars().all()

        return [_session_to_note_row(s) for s in sessions]

    # -------------------------------------------------------------------------
    # LISTAR TAREAS
    # -------------------------------------------------------------------------

    async def list_tasks(
        self,
        *,
        user_id: str,
        only_pending: bool,
        only_with_due_date: bool,
        due_before: Optional[datetime],
        limit: int,
        offset: int,
    ) -> List[TaskRow]:
        async with await get_primary_session() as db:
            q = select(SessionItem).where(
                and_(
                    SessionItem.user_id == user_id,
                    SessionItem.source == _CLASS_NOTE_SOURCE,
                    SessionItem.item_type == SessionItemType.TASK,
                )
            )
            if only_pending:
                q = q.where(SessionItem.status != SessionItemStatus.COMPLETED)
            if only_with_due_date:
                q = q.where(SessionItem.due_date.isnot(None))
            if due_before:
                q = q.where(SessionItem.due_date <= due_before)

            q = q.order_by(SessionItem.due_date.asc().nullslast()).offset(offset).limit(limit)
            result = await db.execute(q)
            items = result.scalars().all()

        return [_item_to_task_row(it) for it in items]

    # -------------------------------------------------------------------------
    # ACTUALIZAR TAREA
    # -------------------------------------------------------------------------

    async def update_task(
        self,
        *,
        user_id: str,
        task_id: str,
        done: Optional[bool],
        due_date: Optional[datetime],
        priority: Optional[int],
    ) -> TaskRow:
        async with await get_primary_session() as db:
            item = await db.get(SessionItem, task_id)
            if not item or item.user_id != user_id:
                raise KeyError("task_not_found")

            if done is not None:
                item.status = (
                    SessionItemStatus.COMPLETED if done else SessionItemStatus.SUGGESTED
                )
            if due_date is not None:
                item.due_date = due_date
            if priority is not None:
                item.priority = str(priority)

            await db.commit()
            await db.refresh(item)

        return _item_to_task_row(item)

    # -------------------------------------------------------------------------
    # ELIMINAR NOTA
    # -------------------------------------------------------------------------

    async def delete_note(self, *, user_id: str, note_id: str) -> bool:
        async with await get_primary_session() as db:
            s = await db.get(RecordingSession, note_id)
            if not s or s.user_id != user_id:
                return False

            # Eliminar items primero
            await db.execute(
                delete(SessionItem).where(
                    and_(
                        SessionItem.session_id == note_id,
                        SessionItem.user_id == user_id,
                    )
                )
            )
            await db.delete(s)
            await db.commit()

        logger.info(f"🗑️ Nota eliminada de Nhost: {note_id}")
        return True

    # -------------------------------------------------------------------------
    # ACTUALIZAR NOTA
    # -------------------------------------------------------------------------

    async def update_note(
        self,
        *,
        user_id: str,
        note_id: str,
        title: Optional[str] = None,
        transcript: Optional[str] = None,
        summary: Optional[str] = None,
        key_points: Optional[List[str]] = None,
    ) -> Optional[NoteRow]:
        async with await get_primary_session() as db:
            s = await db.get(RecordingSession, note_id)
            if not s or s.user_id != user_id:
                return None

            if title is not None:
                s.title = title
            if transcript is not None:
                s.transcript = transcript
            if summary is not None:
                s.summary = summary
            if key_points is not None:
                raw = s.extracted_state or {}
                if isinstance(raw, str):
                    try:
                        raw = json.loads(raw)
                    except Exception:
                        raw = {}
                raw["key_points"] = key_points
                s.extracted_state = raw
            s.updated_at = _utcnow()

            await db.commit()
            await db.refresh(s)

        return _session_to_note_row(s)
