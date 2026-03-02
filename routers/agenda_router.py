from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.db_enterprise import get_db_session, get_primary_session
from models.models import (
    AgendaChunk,
    AgendaItem,
    AgendaItemStatus,
    AgendaItemType,
    AgendaSession,
)
from utils.auth import get_current_user, verify_token


router = APIRouter(prefix="/api/agenda", tags=["Agenda"])


class CreateAgendaSessionRequest(BaseModel):
    class_name: str = Field(..., min_length=1, max_length=200)
    teacher_name: Optional[str] = Field(None, max_length=200)
    teacher_email: Optional[str] = Field(None, max_length=200)
    topic_hint: Optional[str] = Field(None, max_length=300)
    session_datetime: Optional[datetime] = None
    timezone: Optional[str] = Field(None, max_length=64)


class CreateAgendaSessionResponse(BaseModel):
    session_id: str
    status: str


class AppendChunkRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    t_start_ms: Optional[int] = None
    t_end_ms: Optional[int] = None


class AgendaItemDto(BaseModel):
    id: str
    item_type: str
    status: str
    title: Optional[str] = None
    content: str
    datetime_start: Optional[datetime] = None
    datetime_end: Optional[datetime] = None
    due_date: Optional[datetime] = None
    priority: Optional[int] = None
    order_index: int
    important: bool
    source: str
    confidence: Optional[float] = None
    item_metadata: Dict[str, Any] = Field(default_factory=dict)


class AgendaSessionDto(BaseModel):
    id: str
    status: str
    class_name: str
    teacher_name: Optional[str] = None
    teacher_email: Optional[str] = None
    topic_hint: Optional[str] = None
    session_datetime: datetime
    timezone: Optional[str] = None
    live_transcript: str
    items: List[AgendaItemDto] = Field(default_factory=list)


class UpdateAgendaItemRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=400)
    content: Optional[str] = Field(None, max_length=20000)
    status: Optional[AgendaItemStatus] = None
    important: Optional[bool] = None
    priority: Optional[int] = None
    order_index: Optional[int] = None
    datetime_start: Optional[datetime] = None
    datetime_end: Optional[datetime] = None
    due_date: Optional[datetime] = None


class CreateAgendaItemRequest(BaseModel):
    item_type: AgendaItemType
    content: str = Field(..., min_length=1, max_length=20000)
    title: Optional[str] = Field(None, max_length=400)
    datetime_start: Optional[datetime] = None
    datetime_end: Optional[datetime] = None
    due_date: Optional[datetime] = None
    priority: Optional[int] = None
    order_index: int = 0
    important: bool = False


class FinalizeResponse(BaseModel):
    status: str


# In-memory throttling to keep it fast/cheap
_session_ai_lock: Dict[str, asyncio.Lock] = {}
_session_last_ai_ts: Dict[str, float] = {}


def _now_ts() -> float:
    return asyncio.get_running_loop().time()


async def _get_session_or_404(db: AsyncSession, user_id: str, session_id: str) -> AgendaSession:
    res = await db.execute(
        select(AgendaSession).where(and_(AgendaSession.id == session_id, AgendaSession.user_id == user_id))
    )
    session = res.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    return session


def _item_to_dto(item: AgendaItem) -> AgendaItemDto:
    return AgendaItemDto(
        id=item.id,
        item_type=item.item_type.value if hasattr(item.item_type, "value") else str(item.item_type),
        status=item.status.value if hasattr(item.status, "value") else str(item.status),
        title=item.title,
        content=item.content,
        datetime_start=item.datetime_start,
        datetime_end=item.datetime_end,
        due_date=item.due_date,
        priority=item.priority,
        order_index=item.order_index,
        important=bool(item.important),
        source=item.source,
        confidence=item.confidence,
        item_metadata=item.item_metadata or {},
    )


@router.post("/sessions", response_model=CreateAgendaSessionResponse)
async def create_agenda_session(
    payload: CreateAgendaSessionRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_primary_session),
):
    session = AgendaSession(
        user_id=str(user.id) if hasattr(user, "id") else str(user.get("user_id")),
        class_name=payload.class_name,
        teacher_name=payload.teacher_name,
        teacher_email=payload.teacher_email,
        topic_hint=payload.topic_hint,
        session_datetime=payload.session_datetime or datetime.utcnow(),
        timezone=payload.timezone,
        status="recording",
        live_transcript="",
        extracted_state={},
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return CreateAgendaSessionResponse(session_id=session.id, status=session.status)


@router.get("/sessions/{session_id}", response_model=AgendaSessionDto)
async def get_agenda_session(
    session_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_primary_session),
):
    user_id = str(user.id) if hasattr(user, "id") else str(user.get("user_id"))
    session = await _get_session_or_404(db, user_id, session_id)

    items_res = await db.execute(
        select(AgendaItem)
        .where(and_(AgendaItem.session_id == session_id, AgendaItem.user_id == user_id))
        .order_by(AgendaItem.order_index.asc(), AgendaItem.created_at.asc())
    )
    items = items_res.scalars().all()

    return AgendaSessionDto(
        id=session.id,
        status=session.status,
        class_name=session.class_name,
        teacher_name=session.teacher_name,
        teacher_email=session.teacher_email,
        topic_hint=session.topic_hint,
        session_datetime=session.session_datetime,
        timezone=session.timezone,
        live_transcript=session.live_transcript,
        items=[_item_to_dto(i) for i in items],
    )


@router.post("/sessions/{session_id}/chunks")
async def append_chunk(
    session_id: str,
    payload: AppendChunkRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_primary_session),
):
    user_id = str(user.id) if hasattr(user, "id") else str(user.get("user_id"))
    session = await _get_session_or_404(db, user_id, session_id)

    chunk = AgendaChunk(
        session_id=session.id,
        user_id=user_id,
        text=payload.text,
        t_start_ms=payload.t_start_ms,
        t_end_ms=payload.t_end_ms,
    )
    db.add(chunk)

    new_transcript = (session.live_transcript or "") + ("\n" if session.live_transcript else "") + payload.text
    await db.execute(
        update(AgendaSession)
        .where(and_(AgendaSession.id == session_id, AgendaSession.user_id == user_id))
        .values(live_transcript=new_transcript)
    )

    await db.commit()

    return {"ok": True}


@router.post("/sessions/{session_id}/items", response_model=AgendaItemDto)
async def create_item(
    session_id: str,
    payload: CreateAgendaItemRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_primary_session),
):
    user_id = str(user.id) if hasattr(user, "id") else str(user.get("user_id"))
    _ = await _get_session_or_404(db, user_id, session_id)

    item = AgendaItem(
        session_id=session_id,
        user_id=user_id,
        item_type=payload.item_type,
        status=AgendaItemStatus.CONFIRMED,
        title=payload.title,
        content=payload.content,
        datetime_start=payload.datetime_start,
        datetime_end=payload.datetime_end,
        due_date=payload.due_date,
        priority=payload.priority,
        order_index=payload.order_index,
        important=payload.important,
        source="user",
        confidence=None,
        item_metadata={},
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _item_to_dto(item)


@router.patch("/sessions/{session_id}/items/{item_id}", response_model=AgendaItemDto)
async def update_item(
    session_id: str,
    item_id: str,
    payload: UpdateAgendaItemRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_primary_session),
):
    user_id = str(user.id) if hasattr(user, "id") else str(user.get("user_id"))

    res = await db.execute(
        select(AgendaItem).where(
            and_(AgendaItem.id == item_id, AgendaItem.session_id == session_id, AgendaItem.user_id == user_id)
        )
    )
    item = res.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="item_not_found")

    values: Dict[str, Any] = {}
    for k, v in payload.model_dump(exclude_unset=True).items():
        values[k] = v

    if values:
        await db.execute(
            update(AgendaItem)
            .where(and_(AgendaItem.id == item_id, AgendaItem.user_id == user_id))
            .values(**values)
        )
        await db.commit()

    res2 = await db.execute(
        select(AgendaItem).where(
            and_(AgendaItem.id == item_id, AgendaItem.session_id == session_id, AgendaItem.user_id == user_id)
        )
    )
    item2 = res2.scalar_one()
    return _item_to_dto(item2)


@router.delete("/sessions/{session_id}/items/{item_id}")
async def delete_item(
    session_id: str,
    item_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_primary_session),
):
    user_id = str(user.id) if hasattr(user, "id") else str(user.get("user_id"))
    await db.execute(
        delete(AgendaItem).where(
            and_(AgendaItem.id == item_id, AgendaItem.session_id == session_id, AgendaItem.user_id == user_id)
        )
    )
    await db.commit()
    return {"ok": True}


@router.post("/sessions/{session_id}/finalize", response_model=FinalizeResponse)
async def finalize_session(
    session_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_primary_session),
):
    user_id = str(user.id) if hasattr(user, "id") else str(user.get("user_id"))
    _ = await _get_session_or_404(db, user_id, session_id)

    await db.execute(
        update(AgendaSession)
        .where(and_(AgendaSession.id == session_id, AgendaSession.user_id == user_id))
        .values(status="done")
    )
    await db.commit()
    return FinalizeResponse(status="done")


async def _extract_incremental_agenda(transcript: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """MVP: reuse existing segmented extractor; returns normalized state."""
    try:
        from notes_grpc.extractor import extract_note_segmented
        from notes_grpc.siliconflow_client import SiliconFlowClient

        client = SiliconFlowClient()
        extracted = await extract_note_segmented(client=client, transcript=transcript, title_hint="")

        return {
            "summary": extracted.summary,
            "lecture_notes": getattr(extracted, "lecture_notes", ""),
            "key_points": extracted.key_points,
            "tasks": [
                {
                    "text": t.text,
                    "due_date": t.due_date.isoformat() if getattr(t, "due_date", None) else None,
                    "priority": getattr(t, "priority", None),
                }
                for t in (extracted.tasks or [])
            ],
        }
    except Exception:
        return {}


@router.websocket("/live/{session_id}/ws")
async def live_session_ws(websocket: WebSocket, session_id: str):
    """JWT-authenticated realtime session.

    Token can be provided via:
    - query param: ?token=...
    - header: Authorization: Bearer ...
    """
    token = websocket.query_params.get("token")
    if not token:
        auth = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
        if auth and auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()

    if not token:
        await websocket.close(code=1008)
        return

    try:
        payload = await verify_token(token)
        user_id = str(payload.get("sub") or "")
        if not user_id:
            await websocket.close(code=1008)
            return
    except Exception:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "transcript_chunk":
                text = (msg.get("text") or "").strip()
                if not text:
                    continue

                async with get_db_session() as db:
                    session = await _get_session_or_404(db, user_id, session_id)

                    chunk = AgendaChunk(
                        session_id=session.id,
                        user_id=user_id,
                        text=text,
                        t_start_ms=msg.get("t_start_ms"),
                        t_end_ms=msg.get("t_end_ms"),
                    )
                    db.add(chunk)

                    transcript = (session.live_transcript or "") + ("\n" if session.live_transcript else "") + text
                    await db.execute(
                        update(AgendaSession)
                        .where(and_(AgendaSession.id == session_id, AgendaSession.user_id == user_id))
                        .values(live_transcript=transcript)
                    )

                    await db.commit()

                # Throttle AI extraction
                lock = _session_ai_lock.setdefault(session_id, asyncio.Lock())
                async with lock:
                    now = _now_ts()
                    last = _session_last_ai_ts.get(session_id, 0.0)
                    min_interval = float(msg.get("min_ai_interval_sec") or 6.0)

                    if now - last < min_interval:
                        await websocket.send_text(json.dumps({"event": "ack", "ok": True}))
                        continue

                    async with get_db_session() as db2:
                        session2 = await _get_session_or_404(db2, user_id, session_id)
                        state = session2.extracted_state or {}
                        extracted = await _extract_incremental_agenda(session2.live_transcript or "", state)

                        if extracted:
                            await db2.execute(
                                update(AgendaSession)
                                .where(and_(AgendaSession.id == session_id, AgendaSession.user_id == user_id))
                                .values(extracted_state=extracted)
                            )

                            # Replace AI-generated items (preserve user items)
                            await db2.execute(
                                delete(AgendaItem).where(
                                    and_(
                                        AgendaItem.session_id == session_id,
                                        AgendaItem.user_id == user_id,
                                        AgendaItem.source == "ai",
                                        AgendaItem.item_type.in_(
                                            [
                                                AgendaItemType.SUMMARY,
                                                AgendaItemType.KEY_POINT,
                                                AgendaItemType.TASK,
                                            ]
                                        ),
                                    )
                                )
                            )

                            order = 0
                            notes_text = (extracted.get("lecture_notes") or "").strip()
                            summary = (extracted.get("summary") or "").strip()
                            main_text = notes_text or summary
                            if main_text:
                                db2.add(
                                    AgendaItem(
                                        session_id=session_id,
                                        user_id=user_id,
                                        item_type=AgendaItemType.SUMMARY,
                                        status=AgendaItemStatus.SUGGESTED,
                                        title=None,
                                        content=main_text,
                                        order_index=order,
                                        important=False,
                                        source="ai",
                                        confidence=None,
                                        item_metadata={},
                                    )
                                )
                                order += 1

                            for kp in extracted.get("key_points") or []:
                                kp_text = str(kp).strip()
                                if not kp_text:
                                    continue
                                db2.add(
                                    AgendaItem(
                                        session_id=session_id,
                                        user_id=user_id,
                                        item_type=AgendaItemType.KEY_POINT,
                                        status=AgendaItemStatus.SUGGESTED,
                                        title=None,
                                        content=kp_text,
                                        order_index=order,
                                        important=False,
                                        source="ai",
                                        confidence=None,
                                        item_metadata={},
                                    )
                                )
                                order += 1

                            for t in extracted.get("tasks") or []:
                                text_t = str(t.get("text") or "").strip() if isinstance(t, dict) else str(t).strip()
                                if not text_t:
                                    continue
                                meta: Dict[str, Any] = {}
                                due_date = None
                                priority = None
                                if isinstance(t, dict):
                                    meta = {k: v for k, v in t.items() if k not in {"text"}}
                                    priority = t.get("priority")
                                db2.add(
                                    AgendaItem(
                                        session_id=session_id,
                                        user_id=user_id,
                                        item_type=AgendaItemType.TASK,
                                        status=AgendaItemStatus.SUGGESTED,
                                        title=None,
                                        content=text_t,
                                        due_date=due_date,
                                        priority=priority,
                                        order_index=order,
                                        important=False,
                                        source="ai",
                                        confidence=None,
                                        item_metadata=meta,
                                    )
                                )
                                order += 1

                            await db2.commit()

                    _session_last_ai_ts[session_id] = now

                    await websocket.send_text(
                        json.dumps({"event": "agenda_state", "session_id": session_id, "state": extracted})
                    )

            elif event == "ask_ai":
                question = (msg.get("question") or "").strip()
                if not question:
                    continue

                # MVP: answer using unified chat model with transcript context
                try:
                    from services.gpt_service import chat_with_ai

                    async with get_primary_session() as db:
                        session = await _get_session_or_404(db, user_id, session_id)
                        context = session.live_transcript or ""

                    answer = await chat_with_ai(
                        messages=[
                            {
                                "role": "system",
                                "content": "Eres un asistente académico. Responde usando el contexto de la clase. Si falta info, pregunta.",
                            },
                            {"role": "user", "content": f"Contexto:\n{context}\n\nPregunta:\n{question}"},
                        ],
                        user=user_id,
                        fast_reasoning=True,
                    )

                    await websocket.send_text(
                        json.dumps({"event": "assistant_answer", "question": question, "answer": answer})
                    )
                except Exception:
                    await websocket.send_text(json.dumps({"event": "assistant_answer", "question": question, "answer": ""}))

            else:
                await websocket.send_text(json.dumps({"event": "error", "detail": "unknown_event"}))

    except WebSocketDisconnect:
        return
