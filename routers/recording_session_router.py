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
    
    import asyncio
    audio_queue: asyncio.Queue = asyncio.Queue()
    
    async def audio_processor_worker():
        """Worker secundario: procesa FIFO los audios hacia la IA sin bloquear el WS socket"""
        while True:
            item = await audio_queue.get()
            if item is None:
                audio_queue.task_done()
                break # Señal de fin
            
            chunk_bytes, ts_seconds = item
            try:
                str_text = await recording_session_service.process_audio_chunk(
                    session_id=session_id,
                    user_id=user_id,
                    audio_bytes=chunk_bytes,
                    timestamp_seconds=ts_seconds
                )
                if str_text:
                    try:
                        await websocket.send_json({
                            "type": "transcript",
                            "text": str_text,
                            "timestamp": ts_seconds
                        })
                    except Exception:
                        pass # Exception si el WS se cerró abruptamente
            except Exception as w_e:
                logger.error(f"Error worker IA STT: {w_e}")
            finally:
                audio_queue.task_done()

    start_time = datetime.utcnow()
    audio_buffer = b""
    processor_task = asyncio.create_task(audio_processor_worker())
    
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
                        session = await chat_intent_extractor.execute_scheduled_recording(
                            scheduled_id,
                            requesting_user_id=str(user_id),
                        )
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
                        await websocket.send_json({"type": "processing", "message": "Procesando últimos bytes..."})
                        
                        # Drenar audios pendientes
                        if audio_buffer:
                            elapsed = int((datetime.utcnow() - start_time).total_seconds())
                            await audio_queue.put((audio_buffer, elapsed))
                            audio_buffer = b""
                            
                        # Apagar worker gracefulmente
                        await audio_queue.put(None)
                        if processor_task and not processor_task.done():
                            await processor_task
                        
                        await websocket.send_json({"type": "processing", "message": "Finalizando y extrayendo resumen IA..."})
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
                
                # Despachar cada ~2 segundos de audio y liberar loop
                if len(audio_buffer) >= 32000:
                    elapsed = int((datetime.utcnow() - start_time).total_seconds())
                    # Encolar en memoria asíncrona O(1)
                    await audio_queue.put((audio_buffer, elapsed))
                    audio_buffer = b""

    except WebSocketDisconnect:
        logger.info(f"🔌 WS Desconectado: {session_id}")
    except Exception as e:
        logger.error(f"❌ Error crítico WS: {e}")
        try:
            await websocket.send_json({"type": "error", "message": "internal_error"})
        except Exception: 
            pass
    finally:
        # Cleanup final garantizado si cae la red
        if processor_task and not processor_task.done():
            try:
                # 1. Avisamos al worker que es el fin
                await audio_queue.put(None)
                # 2. Le damos 5s de gracia para que guarde en Base de Datos
                await asyncio.wait_for(processor_task, timeout=5.0)
            except asyncio.TimeoutError:
                # 3. Si se congela y no respeta los 5s, lo destruimos forzosamente (Anti-Zombies)
                logger.warning(f"⚠️ Worker tardó demasiado. Matando proceso forzosamente para prevenir Memory Leak. (Session: {session_id})")
                processor_task.cancel()
            except Exception as e:
                logger.error(f"Error limpiando memory task: {e}")
