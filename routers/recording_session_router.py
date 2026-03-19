"""
🎙️ Recording Session Router - WebSocket unificado y HTTP endpoints.
Unifica Agenda, ClassRecording y Grabaciones Automáticas.
"""
import json
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketState

from utils.auth import get_current_user, verify_token
from services.recording_session_service import recording_session_service
from models.models import RecordingSession, RecordingSessionType, RecordingSessionStatus

logger = logging.getLogger("recording_session_router")

router = APIRouter(prefix="/api/recordings", tags=["Recording Sessions"])

# =============================================
# MODELOS Pydantic
# =============================================

class StartSessionRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    teacher_name: Optional[str] = Field(None, max_length=200)
    session_type: str = Field(default=RecordingSessionType.MANUAL)
    scheduled_id: Optional[str] = None
    language: str = Field(default="es")

class SessionOut(BaseModel):
    id: str
    title: str
    teacher_name: Optional[str]
    session_type: str
    status: str
    transcript: str
    summary: Optional[str]
    started_at: datetime
    ended_at: Optional[datetime]
    duration_seconds: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True

class ListSessionsResponse(BaseModel):
    sessions: List[SessionOut]
    total: int

# =============================================
# HTTP ENDPOINTS
# =============================================

@router.post("/start", response_model=SessionOut)
async def start_session(
    payload: StartSessionRequest,
    user=Depends(get_current_user)
):
    """Inicia una nueva sesión de grabación unificada"""
    session = await recording_session_service.start_session(
        user_id=user["user_id"],
        title=payload.title,
        teacher_name=payload.teacher_name,
        session_type=payload.session_type,
        scheduled_id=payload.scheduled_id,
        language=payload.language
    )
    return session

@router.post("/{session_id}/finalize", response_model=SessionOut)
async def finalize_session(
    session_id: str,
    user=Depends(get_current_user)
):
    """Finaliza y procesa con IA una sesión"""
    session = await recording_session_service.finalize_session(
        session_id=session_id,
        user_id=user["user_id"]
    )
    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")
    return session

@router.get("", response_model=ListSessionsResponse)
async def list_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user=Depends(get_current_user)
):
    """Lista sesiones del usuario"""
    sessions = await recording_session_service.list_user_sessions(
        user_id=user["user_id"],
        limit=limit,
        offset=offset
    )
    return {
        "sessions": sessions,
        "total": len(sessions)
    }

# =============================================
# WEBSOCKET UNIFICADO
# =============================================

@router.websocket("/ws/{session_id}")
async def recording_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket unificado para streaming de audio y transcripción.
    Funciona para sesiones manuales, programadas y de agenda.
    """
    await websocket.accept()
    
    # Auth inicial vía query param
    token = websocket.query_params.get("token")
    user_id = None
    if token:
        try:
            payload = await verify_token(token)
            user_id = payload.get("sub")
        except Exception as e:
            logger.warning(f"Error auth WS: {e}")
            await websocket.close(code=1008)
            return

    if not user_id:
        await websocket.close(code=1008)
        return

    logger.info(f"🎙️ WS Unificado conectado: session={session_id}, user={user_id}")
    
    # VALIDACIÓN DE PROPIEDAD: Asegurar que la sesión pertenece al usuario
    async with get_primary_session() as db_session:
        session_check = await db_session.get(RecordingSession, session_id)
        if not session_check or session_check.user_id != user_id:
            logger.warning(f"🚫 Intento de acceso no autorizado a sesión {session_id} por user {user_id}")
            await websocket.close(code=1008) # Policy Violation
            return
    
    start_time = datetime.utcnow()
    audio_buffer = b""
    
    try:
        while True:
            message = await websocket.receive()
            
            if "text" in message:
                try:
                    data = json.loads(message["text"])
                    msg_type = data.get("type")
                    
                    if msg_type == "start_auto":
                        # Iniciar una sesión programada automáticamente
                        scheduled_id = data.get("scheduled_id")
                        from services.chat_intent_extractor import chat_intent_extractor
                        session = await chat_intent_extractor.execute_scheduled_recording(scheduled_id)
                        if session:
                            session_id = session.id
                            await websocket.send_json({
                                "type": "started",
                                "session_id": session.id,
                                "title": session.title
                            })
                        else:
                            await websocket.send_json({"type": "error", "message": "No se pudo iniciar grabación programada"})
                            break

                    elif msg_type == "end":
                        await websocket.send_json({"type": "processing", "message": "Finalizando y resumiendo..."})
                        session = await recording_session_service.finalize_session(session_id, user_id)
                        if session:
                            await websocket.send_json({
                                "type": "complete",
                                "summary": session.summary,
                                "status": session.status
                            })
                        break
                        
                except Exception as e:
                    logger.error(f"Error en comando WS: {e}")

            elif "bytes" in message:
                chunk = message["bytes"]
                audio_buffer += chunk
                
                # Procesar cada ~2 segundos de audio (32000 bytes aprox para webm/opus)
                if len(audio_buffer) >= 32000:
                    elapsed = int((datetime.utcnow() - start_time).total_seconds())
                    text = await recording_session_service.process_audio_chunk(
                        session_id=session_id,
                        user_id=user_id,
                        audio_bytes=audio_buffer,
                        timestamp_seconds=elapsed
                    )
                    
                    if text:
                        await websocket.send_json({
                            "type": "transcript",
                            "text": text,
                            "timestamp": elapsed
                        })
                    
                    audio_buffer = b""

    except WebSocketDisconnect:
        logger.info(f"🔌 WS Desconectado: {session_id}")
    except Exception as e:
        logger.error(f"❌ Error crítico WS: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except: pass
