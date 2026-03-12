from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import anyio
from fastapi import APIRouter, Depends, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, select, text, update
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

logger = logging.getLogger(__name__)


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


class AppendAudioResponse(BaseModel):
    ok: bool = True
    text: str
    relevance: Dict[str, Any]
    state: Dict[str, Any] = Field(default_factory=dict)
    items: List[AgendaItemDto] = Field(default_factory=list)


# In-memory throttling to keep it fast/cheap
_session_ai_lock: Dict[str, asyncio.Lock] = {}
_session_last_ai_ts: Dict[str, float] = {}


def _now_ts() -> float:
    return asyncio.get_running_loop().time()


async def _get_session_or_404(db: AsyncSession, user_id: str, session_id: str) -> AgendaSession:
    try:
        res = await db.execute(
            select(AgendaSession).where(and_(AgendaSession.id == session_id, AgendaSession.user_id == user_id))
        )
        session = res.scalar_one_or_none()
        if session is None:
            raise HTTPException(status_code=404, detail="session_not_found")
        return session
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Error accediendo a agenda_sessions (tabla puede no existir): {e}")
        raise HTTPException(status_code=503, detail="agenda_service_unavailable")


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
    try:
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
    except Exception as e:
        logger.warning(f"Error creando sesión de agenda (tabla puede no existir): {e}")
        raise HTTPException(status_code=503, detail="agenda_service_unavailable")


@router.get("/sessions", response_model=List[AgendaSessionDto])
async def list_agenda_sessions(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_primary_session),
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
):
    """Listar todas las sesiones de agenda del usuario"""
    try:
        user_id = str(user.id) if hasattr(user, "id") else str(user.get("user_id"))
        
        # Build query
        query = select(AgendaSession).where(AgendaSession.user_id == user_id)
        if status:
            query = query.where(AgendaSession.status == status)
        query = query.order_by(AgendaSession.created_at.desc()).offset(offset).limit(limit)
        
        result = await db.execute(query)
        sessions = result.scalars().all()
        
        # Build DTOs with item counts
        dtos: List[AgendaSessionDto] = []
        for session in sessions:
            items_res = await db.execute(
                select(AgendaItem)
                .where(and_(AgendaItem.session_id == session.id, AgendaItem.user_id == user_id))
                .order_by(AgendaItem.order_index.asc(), AgendaItem.created_at.asc())
            )
            items = items_res.scalars().all()
            
            dtos.append(
                AgendaSessionDto(
                    id=session.id,
                    status=session.status,
                    class_name=session.class_name,
                    teacher_name=session.teacher_name,
                    teacher_email=session.teacher_email,
                    topic_hint=session.topic_hint,
                    session_datetime=session.session_datetime,
                    timezone=session.timezone,
                    live_transcript=session.live_transcript or "",
                    items=[_item_to_dto(i) for i in items],
                )
            )
        
        return dtos
    except Exception as e:
        logger.warning(f"Error listando sesiones de agenda (tabla puede no existir): {e}")
        raise HTTPException(status_code=503, detail="agenda_service_unavailable")


@router.get("/sessions/{session_id}", response_model=AgendaSessionDto)
async def get_agenda_session(
    session_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_primary_session),
):
    try:
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
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Error obteniendo sesión de agenda (tabla puede no existir): {e}")
        raise HTTPException(status_code=503, detail="agenda_service_unavailable")


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


@router.post("/sessions/{session_id}/audio", response_model=AppendAudioResponse)
async def append_audio(
    session_id: str,
    file: UploadFile,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_primary_session),
):
    from services.groq_ai_service import chat_with_ai
    from services.groq_voice_service import transcribe_audio_groq
    
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty_audio_file")

    try:
        text = await transcribe_audio_groq(raw, language="es")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"transcription_failed: {str(e)}")

    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="empty_transcription")

    user_id = str(user.id) if hasattr(user, "id") else str(user.get("user_id"))
    session = await _get_session_or_404(db, user_id, session_id)

    relevance = await _classify_chunk_relevance(text)
    rel_label = str(relevance.get("relevance_label") or "SECUNDARIO")
    rel_signals = relevance.get("relevance_signals") or []

    chunk = AgendaChunk(
        session_id=session.id,
        user_id=user_id,
        text=text,
        t_start_ms=None,
        t_end_ms=None,
        relevance_label=rel_label,
        relevance_reason=relevance.get("relevance_reason"),
        relevance_signals=rel_signals,
        relevance_score=relevance.get("relevance_score"),
    )
    db.add(chunk)

    transcript = (session.live_transcript or "") + ("\n" if session.live_transcript else "") + text
    await db.execute(
        update(AgendaSession)
        .where(and_(AgendaSession.id == session_id, AgendaSession.user_id == user_id))
        .values(live_transcript=transcript)
    )
    await db.commit()

    # Run same extraction pipeline as WS (filtered transcript)
    async with get_db_session() as db2:
        session2 = await _get_session_or_404(db2, user_id, session_id)
        state = session2.extracted_state or {}

        rows = await db2.execute(
            select(AgendaChunk)
            .where(
                and_(
                    AgendaChunk.session_id == session_id,
                    AgendaChunk.user_id == user_id,
                    AgendaChunk.relevance_label.in_(["IMPORTANTE", "SECUNDARIO"]),
                )
            )
            .order_by(AgendaChunk.created_at.asc())
        )
        chunks = rows.scalars().all()
        filtered_transcript = "\n".join([c.text for c in chunks if (c.text or "").strip()]).strip()

        important_signals: List[str] = []
        for c in chunks:
            if (c.relevance_label or "").upper() != "IMPORTANTE":
                continue
            if isinstance(getattr(c, "relevance_signals", None), list):
                important_signals.extend([str(s).strip() for s in (c.relevance_signals or []) if str(s).strip()])
        seen = set()
        important_signals = [s for s in important_signals if not (s.lower() in seen or seen.add(s.lower()))]

        extracted = await _extract_incremental_agenda(filtered_transcript, state)

        if extracted:
            extracted_meta = dict(extracted)
            extracted_meta["relevance"] = {
                "important_signals": important_signals[:50],
            }
            await db2.execute(
                update(AgendaSession)
                .where(and_(AgendaSession.id == session_id, AgendaSession.user_id == user_id))
                .values(extracted_state=extracted_meta)
            )

            await db2.execute(
                delete(AgendaItem).where(
                    and_(
                        AgendaItem.session_id == session_id,
                        AgendaItem.user_id == user_id,
                        AgendaItem.source == "ai",
                        AgendaItem.item_type.in_([AgendaItemType.SUMMARY, AgendaItemType.KEY_POINT, AgendaItemType.TASK]),
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

            signals_joined = " ".join([str(s).lower() for s in (important_signals or [])])
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

                important = False
                important_reason = None
                if any(k in signals_joined for k in ["examen", "quiz", "parcial", "fecha", "entrega", "tarea", "deadline"]):
                    important = True
                    important_reason = "signals"
                if important_reason:
                    meta = dict(meta)
                    meta["important_reason"] = important_reason

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
                        important=important,
                        source="ai",
                        confidence=None,
                        item_metadata=meta,
                    )
                )
                order += 1

            await db2.commit()
            extracted = extracted_meta

        items_res = await db2.execute(
            select(AgendaItem)
            .where(and_(AgendaItem.session_id == session_id, AgendaItem.user_id == user_id))
            .order_by(AgendaItem.order_index.asc(), AgendaItem.created_at.asc())
        )
        items = items_res.scalars().all()

    return AppendAudioResponse(text=text, relevance=relevance, state=extracted or {}, items=[_item_to_dto(i) for i in items])


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


@router.delete("/sessions/{session_id}")
async def delete_agenda_session(
    session_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_primary_session),
):
    """Elimina una sesión de agenda completa con todos sus items y chunks"""
    user_id = str(user.id) if hasattr(user, "id") else str(user.get("user_id"))
    
    # Verificar que existe y pertenece al usuario
    session = await _get_session_or_404(db, user_id, session_id)
    
    # Eliminar items asociados
    await db.execute(
        delete(AgendaItem).where(
            and_(AgendaItem.session_id == session_id, AgendaItem.user_id == user_id)
        )
    )
    
    # Eliminar chunks asociados
    await db.execute(
        delete(AgendaChunk).where(
            and_(AgendaChunk.session_id == session_id, AgendaChunk.user_id == user_id)
        )
    )
    
    # Eliminar la sesión
    await db.execute(
        delete(AgendaSession).where(
            and_(AgendaSession.id == session_id, AgendaSession.user_id == user_id)
        )
    )
    
    await db.commit()
    return {"success": True, "message": "Sesión eliminada", "session_id": session_id}


async def _extract_incremental_agenda(transcript: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """MVP: reuse existing segmented extractor; returns normalized state."""
    try:
        from notes_grpc.extractor import extract_note_segmented
        from notes_grpc.groq_client import GroqClient

        client = GroqClient()
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


async def _classify_chunk_relevance(text: str) -> Dict[str, Any]:
    """Classify a transcript chunk as IMPORTANTE/SECUNDARIO/IRRELEVANTE.

    Returns keys:
    - relevance_label: str
    - relevance_reason: str
    - relevance_signals: list[str]
    - relevance_score: float (0..1)
    """
    try:
        from notes_grpc.groq_client import GroqClient

        client = GroqClient()
        system = (
            "Eres un clasificador de fragmentos de una clase. Devuelve SOLO JSON estricto. "
            "Clasifica relevance_label en: IMPORTANTE, SECUNDARIO, IRRELEVANTE. "
            "IMPORTANTE: definiciones, conceptos clave, tareas/entregables, fechas, examen/quiz, instrucciones del profesor. "
            "SECUNDARIO: ejemplos largos, repeticiones, aclaraciones menores. "
            "IRRELEVANTE: bromas, conversación fuera de tema. "
            "Devuelve schema: {relevance_label:string, relevance_reason:string, relevance_signals:[string], relevance_score:number}. "
            "relevance_score: 0..1."
        )
        user = f"Fragmento:\n{text}\n"
        data = await client.chat_json(system=system, user=user)

        label = data.get("relevance_label")
        if not isinstance(label, str):
            label = "SECUNDARIO"
        label = label.strip().upper()
        if label not in {"IMPORTANTE", "SECUNDARIO", "IRRELEVANTE"}:
            label = "SECUNDARIO"

        reason = data.get("relevance_reason")
        if not isinstance(reason, str):
            reason = ""

        signals_raw = data.get("relevance_signals")
        signals: List[str] = []
        if isinstance(signals_raw, list):
            signals = [str(x).strip() for x in signals_raw if str(x).strip()]

        score = data.get("relevance_score")
        if not isinstance(score, (int, float)):
            score = None

        return {
            "relevance_label": label,
            "relevance_reason": reason.strip(),
            "relevance_signals": signals[:20],
            "relevance_score": float(score) if score is not None else None,
        }
    except Exception:
        return {
            "relevance_label": "SECUNDARIO",
            "relevance_reason": "",
            "relevance_signals": [],
            "relevance_score": None,
        }


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

                relevance = await _classify_chunk_relevance(text)
                rel_label = str(relevance.get("relevance_label") or "SECUNDARIO")
                rel_signals = relevance.get("relevance_signals") or []

                async with get_db_session() as db:
                    session = await _get_session_or_404(db, user_id, session_id)

                    chunk = AgendaChunk(
                        session_id=session.id,
                        user_id=user_id,
                        text=text,
                        t_start_ms=msg.get("t_start_ms"),
                        t_end_ms=msg.get("t_end_ms"),
                        relevance_label=rel_label,
                        relevance_reason=relevance.get("relevance_reason"),
                        relevance_signals=rel_signals,
                        relevance_score=relevance.get("relevance_score"),
                    )
                    db.add(chunk)

                    transcript = (session.live_transcript or "") + ("\n" if session.live_transcript else "") + text
                    await db.execute(
                        update(AgendaSession)
                        .where(and_(AgendaSession.id == session_id, AgendaSession.user_id == user_id))
                        .values(live_transcript=transcript)
                    )

                    await db.commit()

                await websocket.send_text(
                    json.dumps(
                        {
                            "event": "chunk_relevance",
                            "session_id": session_id,
                            "relevance": relevance,
                        }
                    )
                )

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

                        # Build filtered transcript from chunks labeled IMPORTANT/SECONDARY (skip IRRELEVANT)
                        rows = await db2.execute(
                            select(AgendaChunk)
                            .where(
                                and_(
                                    AgendaChunk.session_id == session_id,
                                    AgendaChunk.user_id == user_id,
                                    AgendaChunk.relevance_label.in_(["IMPORTANTE", "SECUNDARIO"]),
                                )
                            )
                            .order_by(AgendaChunk.created_at.asc())
                        )
                        chunks = rows.scalars().all()
                        filtered_transcript = "\n".join([c.text for c in chunks if (c.text or "").strip()]).strip()

                        important_signals: List[str] = []
                        for c in chunks:
                            if (c.relevance_label or "").upper() != "IMPORTANTE":
                                continue
                            if isinstance(getattr(c, "relevance_signals", None), list):
                                important_signals.extend([str(s).strip() for s in (c.relevance_signals or []) if str(s).strip()])
                        # de-dupe
                        seen = set()
                        important_signals = [s for s in important_signals if not (s.lower() in seen or seen.add(s.lower()))]

                        extracted = await _extract_incremental_agenda(filtered_transcript, state)

                        if extracted:
                            extracted_meta = dict(extracted)
                            extracted_meta["relevance"] = {
                                "important_signals": important_signals[:50],
                            }
                            await db2.execute(
                                update(AgendaSession)
                                .where(and_(AgendaSession.id == session_id, AgendaSession.user_id == user_id))
                                .values(extracted_state=extracted_meta)
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

                                # Mark tasks as important if any recent chunk signals indicate deadlines/exams/tasks
                                important = False
                                important_reason = None
                                signals_joined = " ".join([str(s).lower() for s in (important_signals or [])])
                                if any(k in signals_joined for k in ["examen", "quiz", "parcial", "fecha", "entrega", "tarea", "deadline"]):
                                    important = True
                                    important_reason = "signals"
                                if important_reason:
                                    meta = dict(meta)
                                    meta["important_reason"] = important_reason

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
                                        important=important,
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
                    from services.groq_ai_service import chat_with_ai

                    db = await get_primary_session()
                    async with db:
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
                    # Sanitizar respuesta
                    from services.groq_ai_service import sanitize_ai_text
                    answer = sanitize_ai_text(answer)

                    await websocket.send_text(
                        json.dumps({"event": "assistant_answer", "question": question, "answer": answer})
                    )
                except Exception:
                    await websocket.send_text(json.dumps({"event": "assistant_answer", "question": question, "answer": ""}))

            else:
                await websocket.send_text(json.dumps({"event": "error", "detail": "unknown_event"}))

    except WebSocketDisconnect:
        return


# =========================
# ENDPOINTS DE RESÚMENES Y TAREAS
# =========================

@router.get("/today/tasks")
async def get_today_tasks(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_primary_session),
):
    """Obtener todas las tareas importantes del día actual"""
    from datetime import date
    
    user_id = str(user.id) if hasattr(user, "id") else str(user.get("user_id"))
    today = date.today()
    
    stmt = select(AgendaItem).where(
        and_(
            AgendaItem.user_id == user_id,
            AgendaItem.item_type == AgendaItemType.TASK,
            AgendaItem.due_date >= datetime.combine(today, datetime.min.time()),
            AgendaItem.due_date < datetime.combine(today, datetime.max.time()),
            AgendaItem.status != AgendaItemStatus.DONE
        )
    )
    result = await db.execute(stmt)
    items = result.scalars().all()
    
    return {
        "success": True,
        "date": today.isoformat(),
        "tasks": [
            {
                "id": item.id,
                "title": item.title,
                "content": item.content,
                "due_date": item.due_date.isoformat() if item.due_date else None,
                "status": item.status.value,
                "session_id": item.session_id
            }
            for item in items
        ],
        "count": len(items)
    }


@router.get("/upcoming/tasks")
async def get_upcoming_tasks(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_primary_session),
    days: int = 7,
    limit: int = 20,
):
    """Obtener tareas importantes upcoming (próximos N días)"""
    from datetime import date, timedelta
    
    user_id = str(user.id) if hasattr(user, "id") else str(user.get("user_id"))
    today = date.today()
    end_date = today + timedelta(days=days)
    
    stmt = select(AgendaItem).where(
        and_(
            AgendaItem.user_id == user_id,
            AgendaItem.item_type == AgendaItemType.TASK,
            AgendaItem.due_date >= datetime.combine(today, datetime.min.time()),
            AgendaItem.due_date < datetime.combine(end_date, datetime.max.time()),
            AgendaItem.status != AgendaItemStatus.DONE
        )
    ).order_by(AgendaItem.due_date).limit(limit)
    
    result = await db.execute(stmt)
    items = result.scalars().all()
    
    return {
        "success": True,
        "from_date": today.isoformat(),
        "to_date": end_date.isoformat(),
        "tasks": [
            {
                "id": item.id,
                "title": item.title,
                "content": item.content,
                "due_date": item.due_date.isoformat() if item.due_date else None,
                "status": item.status.value,
                "session_id": item.session_id,
                "days_until_due": (item.due_date.date() - today).days if item.due_date else None
            }
            for item in items
        ],
        "count": len(items)
    }


@router.get("/sessions/{session_id}/summary")
async def get_session_summary(
    session_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_primary_session),
):
    """Generar resumen de una sesión de clase"""
    user_id = str(user.id) if hasattr(user, "id") else str(user.get("user_id"))
    
    session = await _get_session_or_404(db, user_id, session_id)
    
    if not session.live_transcript:
        return {
            "success": False,
            "error": "No hay transcripción disponible",
            "error_code": "NO_TRANSCRIPT"
        }
    
    try:
        from services.groq_ai_service import chat_with_ai
        
        summary = await chat_with_ai(
            messages=[
                {
                    "role": "system",
                    "content": "Eres un asistente académico que crea resúmenes de clases. "
                               "Crea un resumen estructurado con: "
                               "1. Temas principales "
                               "2. Puntos clave "
                               "3. Tareas asignadas "
                               "4. Fechas importantes "
                               "Sé conciso pero completo."
                },
                {"role": "user", "content": f"Transcripción de la clase:\n{session.live_transcript}"}
            ],
            user=user_id,
            fast_reasoning=False,
            max_tokens=2000
        )
        # Sanitizar resumen
        from services.groq_ai_service import sanitize_ai_text
        summary = sanitize_ai_text(summary)
        
        return {
            "success": True,
            "session_id": session_id,
            "summary": summary,
            "class_name": session.class_name,
            "created_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/my/day-summary")
async def get_day_summary(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_primary_session),
):
    """Resumen completo del día: sesiones, tareas, puntos clave"""
    from datetime import date
    
    user_id = str(user.id) if hasattr(user, "id") else str(user.get("user_id"))
    today = date.today()
    
    # Obtener sesiones de hoy
    stmt_sessions = select(AgendaSession).where(
        and_(
            AgendaSession.user_id == user_id,
            AgendaSession.created_at >= datetime.combine(today, datetime.min.time()),
            AgendaSession.created_at < datetime.combine(today, datetime.max.time())
        )
    )
    result_sessions = await db.execute(stmt_sessions)
    sessions = result_sessions.scalars().all()
    
    # Obtener tareas de hoy
    stmt_tasks = select(AgendaItem).where(
        and_(
            AgendaItem.user_id == user_id,
            AgendaItem.item_type == AgendaItemType.TASK,
            AgendaItem.due_date >= datetime.combine(today, datetime.min.time()),
            AgendaItem.due_date < datetime.combine(today, datetime.max.time())
        )
    )
    result_tasks = await db.execute(stmt_tasks)
    tasks = result_tasks.scalars().all()
    
    # Obtener puntos clave de hoy
    stmt_points = select(AgendaItem).where(
        and_(
            AgendaItem.user_id == user_id,
            AgendaItem.item_type == AgendaItemType.KEY_POINT,
            AgendaItem.created_at >= datetime.combine(today, datetime.min.time()),
            AgendaItem.created_at < datetime.combine(today, datetime.max.time())
        )
    )
    result_points = await db.execute(stmt_points)
    key_points = result_points.scalars().all()
    
    return {
        "success": True,
        "date": today.isoformat(),
        "sessions": [
            {
                "id": s.id,
                "class_name": s.class_name,
                "topic": s.topic,
                "status": s.status.value,
                "has_transcript": bool(s.live_transcript)
            }
            for s in sessions
        ],
        "tasks_today": [
            {
                "id": t.id,
                "title": t.title,
                "content": t.content,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "status": t.status.value
            }
            for t in tasks
        ],
        "key_points": [
            {
                "id": p.id,
                "title": p.title,
                "content": p.content
            }
            for p in key_points
        ],
        "stats": {
            "sessions_count": len(sessions),
            "tasks_count": len(tasks),
            "tasks_done": sum(1 for t in tasks if t.status == AgendaItemStatus.DONE),
            "key_points_count": len(key_points)
        }
    }


__all__ = ["router"]
