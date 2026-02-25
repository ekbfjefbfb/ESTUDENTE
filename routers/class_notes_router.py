from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.auth import get_current_user

from notes_grpc.config import settings
from notes_grpc.extractor import extract_note_segmented
from notes_grpc.siliconflow_client import SiliconFlowClient
from notes_grpc.storage import Storage


router = APIRouter(prefix="/api/class-notes", tags=["Class Notes"])


_storage: Optional[Storage] = None
_storage_lock = asyncio.Lock()


async def _get_storage() -> Storage:
    global _storage
    if _storage is not None:
        return _storage
    async with _storage_lock:
        if _storage is None:
            s = Storage(settings.SQLITE_PATH)
            await s.init()
            _storage = s
    return _storage


class CreateClassNoteRequest(BaseModel):
    transcript: str = Field(..., min_length=1, max_length=400000)
    title_hint: Optional[str] = Field(None, max_length=200)
    save: bool = Field(default=True)


class TaskOut(BaseModel):
    id: Optional[str] = None
    text: str
    due_date: Optional[str] = None
    done: bool = False
    priority: int = 0


class NoteOut(BaseModel):
    id: Optional[str] = None
    title: str
    transcript: str
    summary: str
    topics: List[str]
    key_points: List[str]
    tasks: List[TaskOut]
    created_at: Optional[str] = None


class ListNotesResponse(BaseModel):
    notes: List[NoteOut]


class ListTasksResponse(BaseModel):
    tasks: List[TaskOut]


async def _extract_topics(*, client: SiliconFlowClient, transcript: str) -> List[str]:
    system = "Return STRICT JSON only. Schema: {topics:[string]}"
    user = (
        "Extract the main class topics (short phrases) from this transcript. "
        "Return 5-15 topics max. Transcript:\n" + transcript
    )
    data = await client.chat_json(system=system, user=user)
    raw = data.get("topics")
    if not isinstance(raw, list):
        return []
    topics: List[str] = []
    for t in raw:
        s = str(t).strip()
        if s:
            topics.append(s[:120])
    # dedupe
    seen = set()
    out: List[str] = []
    for t in topics:
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
        if len(out) >= 15:
            break
    return out


@router.post("/from-transcript", response_model=NoteOut)
async def create_note_from_transcript(
    payload: CreateClassNoteRequest,
    _user=Depends(get_current_user),
):
    title_hint = (payload.title_hint or "").strip()

    client = SiliconFlowClient()
    try:
        extracted = await extract_note_segmented(
            client=client,
            transcript=payload.transcript,
            title_hint=title_hint,
        )
        topics = await _extract_topics(client=client, transcript=payload.transcript)
    finally:
        await client.aclose()

    tasks_out: List[TaskOut] = []
    for t in extracted.tasks:
        tasks_out.append(
            TaskOut(
                text=t.text,
                due_date=t.due_date.isoformat() if t.due_date else None,
                done=False,
                priority=t.priority,
            )
        )

    note_id: Optional[str] = None
    created_at: Optional[str] = None

    if payload.save:
        storage = await _get_storage()
        note_row, task_rows = await storage.create_note(
            title=extracted.title,
            transcript=payload.transcript,
            summary=extracted.summary,
            key_points=extracted.key_points,
            tasks=[
                {
                    "text": t.text,
                    "due_date": t.due_date,
                    "done": False,
                    "priority": t.priority,
                }
                for t in extracted.tasks
            ],
        )
        note_id = note_row.id
        created_at = note_row.created_at.isoformat()

        # patch ids from DB
        tasks_out = []
        for tr in task_rows:
            tasks_out.append(
                TaskOut(
                    id=tr.id,
                    text=tr.text,
                    due_date=tr.due_date.isoformat() if tr.due_date else None,
                    done=tr.done,
                    priority=tr.priority,
                )
            )

    return NoteOut(
        id=note_id,
        title=extracted.title,
        transcript=payload.transcript,
        summary=extracted.summary,
        topics=topics,
        key_points=extracted.key_points,
        tasks=tasks_out,
        created_at=created_at,
    )


@router.get("/{note_id}", response_model=NoteOut)
async def get_note(note_id: str, _user=Depends(get_current_user)):
    storage = await _get_storage()
    got = await storage.get_note(note_id=note_id)
    if not got:
        raise HTTPException(status_code=404, detail="note_not_found")
    note_row, task_rows = got

    tasks_out: List[TaskOut] = []
    for tr in task_rows:
        tasks_out.append(
            TaskOut(
                id=tr.id,
                text=tr.text,
                due_date=tr.due_date.isoformat() if tr.due_date else None,
                done=tr.done,
                priority=tr.priority,
            )
        )

    # topics are not persisted yet
    return NoteOut(
        id=note_row.id,
        title=note_row.title,
        transcript=note_row.transcript,
        summary=note_row.summary,
        topics=[],
        key_points=note_row.key_points,
        tasks=tasks_out,
        created_at=note_row.created_at.isoformat(),
    )


@router.get("", response_model=ListNotesResponse)
async def list_notes(
    limit: int = 20,
    offset: int = 0,
    _user=Depends(get_current_user),
):
    storage = await _get_storage()
    rows = await storage.list_notes(from_ts=None, to_ts=None, limit=min(limit, 100), offset=max(offset, 0))
    out: List[NoteOut] = []
    for r in rows:
        out.append(
            NoteOut(
                id=r.id,
                title=r.title,
                transcript=r.transcript,
                summary=r.summary,
                topics=[],
                key_points=r.key_points,
                tasks=[],
                created_at=r.created_at.isoformat(),
            )
        )
    return ListNotesResponse(notes=out)


@router.get("/tasks", response_model=ListTasksResponse)
async def list_tasks(
    only_pending: bool = True,
    only_with_due_date: bool = False,
    due_before: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    _user=Depends(get_current_user),
):
    storage = await _get_storage()

    due_dt: Optional[datetime] = None
    if due_before:
        try:
            due_dt = datetime.fromisoformat(due_before.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(status_code=400, detail="invalid_due_before")

    rows = await storage.list_tasks(
        only_pending=only_pending,
        only_with_due_date=only_with_due_date,
        due_before=due_dt,
        limit=min(limit, 200),
        offset=max(offset, 0),
    )

    tasks_out: List[TaskOut] = []
    for tr in rows:
        tasks_out.append(
            TaskOut(
                id=tr.id,
                text=tr.text,
                due_date=tr.due_date.isoformat() if tr.due_date else None,
                done=tr.done,
                priority=tr.priority,
            )
        )

    return ListTasksResponse(tasks=tasks_out)
