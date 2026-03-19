from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class NoteRow:
    id: str
    title: str
    transcript: str
    summary: str
    key_points: List[str]
    created_at: datetime


@dataclass
class TaskRow:
    id: str
    note_id: str
    text: str
    due_date: Optional[datetime]
    done: bool
    priority: int


class Storage:
    def __init__(self, sqlite_path: str) -> None:
        self._path = sqlite_path

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA synchronous=NORMAL")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    transcript TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    key_points_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    note_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    due_date TEXT NULL,
                    done INTEGER NOT NULL,
                    priority INTEGER NOT NULL,
                    FOREIGN KEY(note_id) REFERENCES notes(id) ON DELETE CASCADE
                )
                """
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_notes_user_id ON notes(user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_notes_created_at ON notes(created_at)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_note_id ON tasks(note_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date)")
            
            # Migración simple: intentar agregar user_id si no existe
            try:
                await db.execute("ALTER TABLE notes ADD COLUMN user_id TEXT DEFAULT ''")
                await db.execute("ALTER TABLE tasks ADD COLUMN user_id TEXT DEFAULT ''")
            except Exception:
                pass # Ya existen
            
            await db.commit()

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
        note_id = uuid.uuid4().hex
        created_at = created_at or _utcnow()
        created_at_s = created_at.isoformat()

        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO notes(id,user_id,title,transcript,summary,key_points_json,created_at) VALUES(?,?,?,?,?,?,?)",
                (note_id, user_id, title, transcript, summary, json.dumps(key_points, ensure_ascii=False), created_at_s),
            )

            task_rows: List[TaskRow] = []
            for t in tasks:
                task_id = uuid.uuid4().hex
                text = str(t.get("text", "")).strip()
                if not text:
                    continue
                due_date = t.get("due_date")
                due_date_s: Optional[str] = None
                if isinstance(due_date, datetime):
                    due_date_s = due_date.astimezone(timezone.utc).isoformat()
                done = bool(t.get("done", False))
                priority = int(t.get("priority", 0))

                await db.execute(
                    "INSERT INTO tasks(id,user_id,note_id,text,due_date,done,priority) VALUES(?,?,?,?,?,?,?)",
                    (task_id, user_id, note_id, text, due_date_s, 1 if done else 0, priority),
                )
                task_rows.append(
                    TaskRow(
                        id=task_id,
                        user_id=user_id,
                        note_id=note_id,
                        text=text,
                        due_date=datetime.fromisoformat(due_date_s) if due_date_s else None,
                        done=done,
                        priority=priority,
                    )
                )

            await db.commit()

        note = NoteRow(
            id=note_id,
            user_id=user_id,
            title=title,
            transcript=transcript,
            summary=summary,
            key_points=key_points,
            created_at=created_at,
        )
        return note, task_rows

    async def get_note(self, *, user_id: str, note_id: str) -> Optional[Tuple[NoteRow, List[TaskRow]]]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row

            cur = await db.execute("SELECT * FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
            note_row = await cur.fetchone()
            if not note_row:
                return None

            tasks_cur = await db.execute("SELECT * FROM tasks WHERE note_id = ? AND user_id = ? ORDER BY id", (note_id, user_id))
            task_rows_raw = await tasks_cur.fetchall()

        note = NoteRow(
            id=note_row["id"],
            user_id=note_row["user_id"],
            title=note_row["title"],
            transcript=note_row["transcript"],
            summary=note_row["summary"],
            key_points=json.loads(note_row["key_points_json"]),
            created_at=datetime.fromisoformat(note_row["created_at"]),
        )

        tasks: List[TaskRow] = []
        for r in task_rows_raw:
            due = r["due_date"]
            tasks.append(
                TaskRow(
                    id=r["id"],
                    user_id=r["user_id"],
                    note_id=r["note_id"],
                    text=r["text"],
                    due_date=datetime.fromisoformat(due) if due else None,
                    done=bool(r["done"]),
                    priority=int(r["priority"]),
                )
            )

        return note, tasks

    async def list_notes(
        self,
        *,
        user_id: str,
        from_ts: Optional[datetime],
        to_ts: Optional[datetime],
        limit: int,
        offset: int,
    ) -> List[NoteRow]:
        q = "SELECT * FROM notes WHERE user_id = ?"
        args: List[Any] = [user_id]
        clauses: List[str] = []

        if from_ts:
            clauses.append("created_at >= ?")
            args.append(from_ts.astimezone(timezone.utc).isoformat())
        if to_ts:
            clauses.append("created_at <= ?")
            args.append(to_ts.astimezone(timezone.utc).isoformat())

        if clauses:
            q += " AND " + " AND ".join(clauses)

        q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        args.extend([limit, offset])

        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(q, tuple(args))
            rows = await cur.fetchall()

        notes: List[NoteRow] = []
        for r in rows:
            notes.append(
                NoteRow(
                    id=r["id"],
                    user_id=r["user_id"],
                    title=r["title"],
                    transcript=r["transcript"],
                    summary=r["summary"],
                    key_points=json.loads(r["key_points_json"]),
                    created_at=datetime.fromisoformat(r["created_at"]),
                )
            )
        return notes

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
        q = "SELECT * FROM tasks WHERE user_id = ?"
        args: List[Any] = [user_id]
        clauses: List[str] = []

        if only_pending:
            clauses.append("done = 0")
        if only_with_due_date:
            clauses.append("due_date IS NOT NULL")
        if due_before:
            clauses.append("due_date <= ?")
            args.append(due_before.astimezone(timezone.utc).isoformat())

        if clauses:
            q += " AND " + " AND ".join(clauses)

        q += " ORDER BY COALESCE(due_date, '9999-12-31T00:00:00+00:00') ASC LIMIT ? OFFSET ?"
        args.extend([limit, offset])

        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(q, tuple(args))
            rows = await cur.fetchall()

        tasks: List[TaskRow] = []
        for r in rows:
            due = r["due_date"]
            tasks.append(
                TaskRow(
                    id=r["id"],
                    user_id=r["user_id"],
                    note_id=r["note_id"],
                    text=r["text"],
                    due_date=datetime.fromisoformat(due) if due else None,
                    done=bool(r["done"]),
                    priority=int(r["priority"]),
                )
            )
        return tasks

    async def update_task(
        self,
        *,
        user_id: str,
        task_id: str,
        done: Optional[bool],
        due_date: Optional[datetime],
        priority: Optional[int],
    ) -> TaskRow:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row

            cur = await db.execute("SELECT * FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
            row = await cur.fetchone()
            if not row:
                raise KeyError("task_not_found")

            new_done = int(done) if done is not None else int(row["done"])
            new_due: Optional[str]
            if due_date is not None:
                new_due = due_date.astimezone(timezone.utc).isoformat()
            else:
                new_due = row["due_date"]

            new_priority = int(priority) if priority is not None else int(row["priority"])

            await db.execute(
                "UPDATE tasks SET done = ?, due_date = ?, priority = ? WHERE id = ? AND user_id = ?",
                (new_done, new_due, new_priority, task_id, user_id),
            )
            await db.commit()

        return TaskRow(
            id=task_id,
            user_id=user_id,
            note_id=row["note_id"],
            text=row["text"],
            due_date=datetime.fromisoformat(new_due) if new_due else None,
            done=bool(new_done),
            priority=new_priority,
        )

    async def delete_note(self, *, user_id: str, note_id: str) -> bool:
        """Elimina una nota y sus tareas asociadas (cascade)"""
        async with aiosqlite.connect(self._path) as db:
            # Verificar que existe y pertenece al usuario
            cur = await db.execute("SELECT id FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
            row = await cur.fetchone()
            if not row:
                return False
            
            # Eliminar (las tareas se eliminan en cascade por FK si la BD lo soporta, 
            # pero forzamos por user_id por seguridad extra)
            await db.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
            await db.execute("DELETE FROM tasks WHERE note_id = ? AND user_id = ?", (note_id, user_id))
            await db.commit()
            return True

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
        """Actualiza una nota existente. Campos None no se modifican."""
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row

            # Verificar que existe y pertenece al usuario
            cur = await db.execute("SELECT * FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
            row = await cur.fetchone()
            if not row:
                return None

            # Construir update dinámico
            updates: List[str] = []
            args: List[Any] = []
            
            if title is not None:
                updates.append("title = ?")
                args.append(title)
            if transcript is not None:
                updates.append("transcript = ?")
                args.append(transcript)
            if summary is not None:
                updates.append("summary = ?")
                args.append(summary)
            if key_points is not None:
                updates.append("key_points_json = ?")
                args.append(json.dumps(key_points, ensure_ascii=False))

            if not updates:
                # No hay nada que actualizar, devolver nota actual
                return NoteRow(
                    id=row["id"],
                    user_id=row["user_id"],
                    title=row["title"],
                    transcript=row["transcript"],
                    summary=row["summary"],
                    key_points=json.loads(row["key_points_json"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                )

            args.extend([note_id, user_id])
            query = f"UPDATE notes SET {', '.join(updates)} WHERE id = ? AND user_id = ?"
            await db.execute(query, tuple(args))
            await db.commit()

            # Leer nota actualizada
            cur2 = await db.execute("SELECT * FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
            updated = await cur2.fetchone()
            
            return NoteRow(
                id=updated["id"],
                user_id=updated["user_id"],
                title=updated["title"],
                transcript=updated["transcript"],
                summary=updated["summary"],
                key_points=json.loads(updated["key_points_json"]),
                created_at=datetime.fromisoformat(updated["created_at"]),
            )
