"""
🎙️ Class Recording Router - WebSocket streaming + HTTP endpoints
Grabación de clases con transcripción en tiempo real y resumen al final
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketState

from utils.auth import get_current_user, verify_token
from services.class_recording_service import class_recording_service
from models.models import ClassRecording

logger = logging.getLogger("class_recording_router")

router = APIRouter(prefix="/api/class-recordings", tags=["Class Recordings"])


# =============================================
# MODELOS Pydantic
# =============================================

class StartRecordingRequest(BaseModel):
    class_name: str = Field(..., min_length=1, max_length=200, description="Nombre de la clase")
    teacher_name: Optional[str] = Field(None, max_length=200, description="Nombre del profesor")
    language: str = Field(default="es", description="Idioma de la transcripción")


class RecordingOut(BaseModel):
    id: str
    class_name: str
    teacher_name: Optional[str]
    status: str
    transcript: str
    summary: Optional[str]
    transcript_chunks_count: int
    started_at: str
    ended_at: Optional[str]
    duration_seconds: Optional[int]
    created_at: str

    class Config:
        from_attributes = True


class ListRecordingsResponse(BaseModel):
    recordings: list[RecordingOut]
    total: int


# =============================================
# HTTP ENDPOINTS
# =============================================

@router.post("/start", response_model=RecordingOut)
async def start_recording(
    payload: StartRecordingRequest,
    user=Depends(get_current_user)
):
    """
    Inicia una nueva grabación de clase (sin WebSocket, para testing)
    """
    recording = await class_recording_service.start_recording(
        user_id=user["user_id"],
        class_name=payload.class_name,
        teacher_name=payload.teacher_name,
        language=payload.language
    )

    return RecordingOut(
        id=recording.id,
        class_name=recording.class_name,
        teacher_name=recording.teacher_name,
        status=recording.status,
        transcript=recording.transcript,
        summary=recording.summary,
        transcript_chunks_count=recording.transcript_chunks_count,
        started_at=recording.started_at.isoformat(),
        ended_at=recording.ended_at.isoformat() if recording.ended_at else None,
        duration_seconds=recording.duration_seconds,
        created_at=recording.created_at.isoformat()
    )


@router.post("/{recording_id}/finalize", response_model=RecordingOut)
async def finalize_recording(
    recording_id: str,
    user=Depends(get_current_user)
):
    """
    Finaliza una grabación y genera el resumen (para testing sin WS)
    """
    recording = await class_recording_service.finalize_recording(
        recording_id=recording_id,
        user_id=user["user_id"]
    )

    if not recording:
        raise HTTPException(status_code=404, detail="recording_not_found")

    return RecordingOut(
        id=recording.id,
        class_name=recording.class_name,
        teacher_name=recording.teacher_name,
        status=recording.status,
        transcript=recording.transcript,
        summary=recording.summary,
        transcript_chunks_count=recording.transcript_chunks_count,
        started_at=recording.started_at.isoformat(),
        ended_at=recording.ended_at.isoformat() if recording.ended_at else None,
        duration_seconds=recording.duration_seconds,
        created_at=recording.created_at.isoformat()
    )


@router.get("", response_model=ListRecordingsResponse)
async def list_recordings(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None),
    user=Depends(get_current_user)
):
    """
    Lista las grabaciones del usuario
    """
    recordings = await class_recording_service.get_user_recordings(
        user_id=user["user_id"],
        limit=limit,
        offset=offset,
        status=status
    )

    out = []
    for r in recordings:
        out.append(RecordingOut(
            id=r.id,
            class_name=r.class_name,
            teacher_name=r.teacher_name,
            status=r.status,
            transcript=r.transcript,
            summary=r.summary,
            transcript_chunks_count=r.transcript_chunks_count,
            started_at=r.started_at.isoformat(),
            ended_at=r.ended_at.isoformat() if r.ended_at else None,
            duration_seconds=r.duration_seconds,
            created_at=r.created_at.isoformat()
        ))

    return ListRecordingsResponse(recordings=out, total=len(out))


@router.get("/{recording_id}", response_model=RecordingOut)
async def get_recording(
    recording_id: str,
    user=Depends(get_current_user)
):
    """
    Obtiene detalle de una grabación específica
    """
    recording = await class_recording_service.get_recording_by_id(
        recording_id=recording_id,
        user_id=user["user_id"]
    )

    if not recording:
        raise HTTPException(status_code=404, detail="recording_not_found")

    return RecordingOut(
        id=recording.id,
        class_name=recording.class_name,
        teacher_name=recording.teacher_name,
        status=recording.status,
        transcript=recording.transcript,
        summary=recording.summary,
        transcript_chunks_count=recording.transcript_chunks_count,
        started_at=recording.started_at.isoformat(),
        ended_at=recording.ended_at.isoformat() if recording.ended_at else None,
        duration_seconds=recording.duration_seconds,
        created_at=recording.created_at.isoformat()
    )


@router.delete("/{recording_id}")
async def delete_recording(
    recording_id: str,
    user=Depends(get_current_user)
):
    """
    Elimina una grabación
    """
    deleted = await class_recording_service.delete_recording(
        recording_id=recording_id,
        user_id=user["user_id"]
    )

    if not deleted:
        raise HTTPException(status_code=404, detail="recording_not_found")

    return {"success": True, "message": "Grabación eliminada"}


# =============================================
# WEBSOCKET ENDPOINT - Transmisión en tiempo real
# =============================================

MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10MB max audio


@router.websocket("/ws/{user_id}")
async def class_recording_websocket(websocket: WebSocket, user_id: str):
    """
    WebSocket para grabación de clase en tiempo real

    Flujo:
    1. Cliente envía: {"type": "start", "class_name": "...", "teacher_name": "..."}
    2. Backend responde: {"type": "started", "recording_id": "..."}
    3. Cliente envía audio en chunks binarios
    4. Backend responde: {"type": "transcript", "text": "...", "timestamp": N}
    5. Cliente envía: {"type": "end"}
    6. Backend genera resumen y responde: {"type": "complete", "summary": "...", "transcript": "..."}
    """
    await websocket.accept()
    logger.info(f"🎙️ WebSocket de grabación conectado: user_id={user_id}")

    # Estado de la grabación
    recording_id: Optional[str] = None
    start_time: Optional[datetime] = None
    audio_buffer: bytes = b""
    is_recording = False

    try:
        while True:
            # Recibir mensaje (puede ser texto o binario)
            message = await websocket.receive()

            # Mensaje de texto (comandos)
            if "text" in message:
                data = json.loads(message["text"])
                msg_type = data.get("type")

                # Iniciar grabación
                if msg_type == "start":
                    if is_recording:
                        await _send_ws_json(websocket, {
                            "type": "error",
                            "message": "Grabación ya en curso"
                        })
                        continue

                    class_name = data.get("class_name", "Clase sin nombre")
                    teacher_name = data.get("teacher_name")
                    language = data.get("language", "es")

                    # Crear grabación
                    recording = await class_recording_service.start_recording(
                        user_id=user_id,
                        class_name=class_name,
                        teacher_name=teacher_name,
                        language=language
                    )

                    recording_id = recording.id
                    start_time = datetime.utcnow()
                    is_recording = True
                    audio_buffer = b""

                    await _send_ws_json(websocket, {
                        "type": "started",
                        "recording_id": recording_id,
                        "class_name": class_name,
                        "timestamp": _now_iso()
                    })

                    logger.info(f"🎙️ Grabación iniciada vía WS: {recording_id}")

                # Finalizar grabación
                elif msg_type == "end":
                    if not is_recording or not recording_id:
                        await _send_ws_json(websocket, {
                            "type": "error",
                            "message": "No hay grabación activa"
                        })
                        continue

                    # Procesar audio restante en buffer
                    if len(audio_buffer) > 100:
                        elapsed = int((datetime.utcnow() - start_time).total_seconds())
                        text = await class_recording_service.process_audio_chunk(
                            recording_id=recording_id,
                            user_id=user_id,
                            audio_bytes=audio_buffer,
                            timestamp_seconds=elapsed
                        )
                        if text:
                            await _send_ws_json(websocket, {
                                "type": "transcript",
                                "text": text,
                                "timestamp": elapsed,
                                "is_final": False
                            })

                    # Notificar que estamos generando resumen
                    await _send_ws_json(websocket, {
                        "type": "processing",
                        "message": "Generando resumen...",
                        "timestamp": _now_iso()
                    })

                    # Finalizar y generar resumen
                    recording = await class_recording_service.finalize_recording(
                        recording_id=recording_id,
                        user_id=user_id
                    )

                    if recording:
                        await _send_ws_json(websocket, {
                            "type": "complete",
                            "recording_id": recording_id,
                            "status": recording.status,
                            "transcript": recording.transcript,
                            "summary": recording.summary,
                            "duration_seconds": recording.duration_seconds,
                            "timestamp": _now_iso()
                        })

                        logger.info(f"✅ Grabación completada: {recording_id}")
                    else:
                        await _send_ws_json(websocket, {
                            "type": "error",
                            "message": "Error al finalizar grabación"
                        })

                    is_recording = False
                    recording_id = None

                # Ping/Pong para mantener conexión
                elif msg_type == "ping":
                    await _send_ws_json(websocket, {
                        "type": "pong",
                        "timestamp": _now_iso()
                    })

            # Mensaje binario (audio)
            elif "bytes" in message:
                if not is_recording or not recording_id:
                    continue

                chunk = message["bytes"]

                if not isinstance(chunk, bytes):
                    logger.warning(f"Chunk de audio inválido: {type(chunk)}")
                    continue

                # Acumular en buffer
                audio_buffer += chunk

                # Procesar cuando tengamos suficiente audio (~5-10 segundos)
                # O cuando el buffer sea muy grande
                if len(audio_buffer) > 32000 or len(audio_buffer) > MAX_AUDIO_BYTES:  # ~2 segundos de audio
                    elapsed = int((datetime.utcnow() - start_time).total_seconds())

                    text = await class_recording_service.process_audio_chunk(
                        recording_id=recording_id,
                        user_id=user_id,
                        audio_bytes=audio_buffer,
                        timestamp_seconds=elapsed
                    )

                    if text:
                        await _send_ws_json(websocket, {
                            "type": "transcript",
                            "text": text,
                            "timestamp": elapsed,
                            "is_final": False
                        })

                    # Limpiar buffer
                    audio_buffer = b""

    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket desconectado: user_id={user_id}")

        # Si había grabación activa, intentar finalizarla
        if is_recording and recording_id:
            try:
                logger.info(f"⚠️ Grabación {recording_id} interrumpida por desconexión")
                # No generamos resumen, solo marcamos como error
                # El usuario puede reanudar o la grabación queda incompleta
            except Exception as e:
                logger.error(f"Error manejando desconexión: {e}")

    except Exception as e:
        logger.error(f"❌ Error en WebSocket de grabación: {e}")
        try:
            await _send_ws_json(websocket, {
                "type": "error",
                "message": str(e)
            })
        except:
            pass


# Helper functions

async def _send_ws_json(websocket: WebSocket, data: dict):
    """Envía mensaje JSON por WebSocket si está conectado"""
    try:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json(data)
    except Exception as e:
        logger.debug(f"Error enviando WS: {e}")


def _now_iso() -> str:
    """Timestamp ISO actual"""
    return datetime.utcnow().isoformat()
