"""
🗓️ Scheduled Recording Router - API para agenda inteligente automatizada
Endpoints para programar, consultar y ejecutar grabaciones automáticas
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, and_

from utils.auth import get_current_user
from utils.auth import create_access_token
from models.models import ScheduledRecording, UserContext, User
from database.db_enterprise import get_primary_session
from services.chat_intent_extractor import chat_intent_extractor, ScheduleIntent
from services.recording_session_service import recording_session_service
from services.user_context_service import user_context_service

logger = logging.getLogger("scheduled_recording_router")

router = APIRouter(prefix="/api/scheduled-recordings", tags=["Scheduled Recordings"])


# =============================================
# MODELOS Pydantic
# =============================================

class ScheduleFromChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000, description="Mensaje del usuario")


class ScheduleIntentResponse(BaseModel):
    has_intent: bool
    class_name: Optional[str]
    teacher_name: Optional[str]
    scheduled_at: Optional[str]
    confidence: float
    needs_confirmation: bool
    reasoning: str
    created_recording_id: Optional[str]


class ScheduledRecordingOut(BaseModel):
    id: str
    class_name: str
    teacher_name: Optional[str]
    scheduled_at: str
    timezone: str
    status: str
    location_name: Optional[str]
    ai_confidence: float
    created_at: str


class PendingRecordingResponse(BaseModel):
    should_record: bool
    scheduled_recording: Optional[ScheduledRecordingOut]
    recording_token: Optional[str]
    message: str


class UpdateLocationRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    battery_level: Optional[int] = Field(None, ge=0, le=100)


# =============================================
# ENDPOINTS
# =============================================

@router.post("/from-chat", response_model=ScheduleIntentResponse)
async def schedule_from_chat(
    payload: ScheduleFromChatRequest,
    user=Depends(get_current_user)
):
    """
    Procesa mensaje de chat y crea scheduled recording si detecta intención.
    
    Ejemplo mensaje: "Mañana a las 2:30 tengo clase de Cálculo"
    """
    # Obtener contexto del usuario
    async with get_primary_session() as session:
        user_context = await session.get(UserContext, user["user_id"])

        recent_classes = []
        try:
            recent_q = (
                select(ScheduledRecording.class_name, ScheduledRecording.teacher_name)
                .where(ScheduledRecording.user_id == user["user_id"])
                .order_by(desc(ScheduledRecording.scheduled_at))
                .limit(5)
            )
            recent_res = await session.execute(recent_q)
            for class_name, teacher_name in recent_res.all():
                cn = str(class_name or "").strip()
                tn = str(teacher_name or "").strip()
                if cn:
                    recent_classes.append(
                        {
                            "class_name": cn[:200],
                            "teacher_name": tn[:200] if tn else None,
                        }
                    )
        except Exception:
            recent_classes = []
        
        context = {
            "timezone": user_context.timezone if user_context else "America/Mexico_City",
            "location": {
                "lat": user_context.current_location_lat if user_context else None,
                "lng": user_context.current_location_lng if user_context else None
            } if user_context else None,
            "recent_classes": recent_classes  # TODO: Obtener clases recientes del usuario
        }
    
    # Extraer intención
    intent = await chat_intent_extractor.extract_schedule_intent(
        message=payload.message,
        user_context=context
    )
    
    # Crear scheduled recording si es necesario
    created_id = None
    if intent.has_scheduling_intent and not intent.needs_confirmation:
        recording = await chat_intent_extractor.create_scheduled_recording(
            user_id=user["user_id"],
            intent=intent,
            original_message=payload.message
        )
        if recording:
            created_id = recording.id
    
    return ScheduleIntentResponse(
        has_intent=intent.has_scheduling_intent,
        class_name=intent.class_name,
        teacher_name=intent.teacher_name,
        scheduled_at=intent.scheduled_datetime.isoformat() if intent.scheduled_datetime else None,
        confidence=intent.confidence,
        needs_confirmation=intent.needs_confirmation,
        reasoning=intent.reasoning,
        created_recording_id=created_id
    )


@router.get("/pending", response_model=PendingRecordingResponse)
async def get_pending_recording(
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lng: Optional[float] = Query(None, ge=-180, le=180),
    battery: Optional[int] = Query(None, ge=0, le=100),
    device_id: Optional[str] = Header(None),
    user=Depends(get_current_user)
):
    """
    Endpoint para la app móvil consultar si debe iniciar grabación automática.
    
    La app llama este endpoint cada X minutos (ej: cada 2 min).
    Si hay una grabación programada para ahora, responde con should_record=true.
    """
    now = datetime.utcnow()
    window_start = now - timedelta(minutes=2)  # 2 minutos de margen
    window_end = now + timedelta(minutes=2)
    
    async with get_primary_session() as session:
        # Buscar scheduled recordings pendientes en ventana de tiempo
        query = select(ScheduledRecording).where(
            and_(
                ScheduledRecording.user_id == user["user_id"],
                ScheduledRecording.status == "pending",
                ScheduledRecording.scheduled_at >= window_start,
                ScheduledRecording.scheduled_at <= window_end
            )
        ).order_by(ScheduledRecording.scheduled_at).with_for_update(skip_locked=True)
        
        result = await session.execute(query)
        pending = result.scalar_one_or_none()
        
        if not pending:
            return PendingRecordingResponse(
                should_record=False,
                scheduled_recording=None,
                recording_token=None,
                message="No hay grabaciones programadas para ahora"
            )
        
        # Verificar ubicación si está configurada
        if pending.location_lat is not None and pending.location_lng is not None:
            if lat is None or lng is None:
                return PendingRecordingResponse(
                    should_record=False,
                    scheduled_recording=None,
                    recording_token=None,
                    message="Se requiere ubicación para esta grabación"
                )
            
            # Calcular distancia (aproximada)
            distance = _calculate_distance(lat, lng, pending.location_lat, pending.location_lng)
            if distance > pending.location_radius_meters:
                return PendingRecordingResponse(
                    should_record=False,
                    scheduled_recording=None,
                    recording_token=None,
                    message=f"Debes estar en {pending.location_name or 'la ubicación'} para grabar (distancia: {int(distance)}m)"
                )
        
        # Verificar batería
        if battery is not None and battery < 20:
            return PendingRecordingResponse(
                should_record=False,
                scheduled_recording=None,
                recording_token=None,
                message="Batería muy baja. Conecta el cargador para grabar automáticamente."
            )
        
        # Actualizar estado a "recording"
        pending.status = "recording"
        pending.executed_at = now
        await session.commit()
        
        # Generar token temporal para WebSocket (1 hora de validez)
        recording_token = await create_access_token(
            {
                "sub": str(user["user_id"]),
                "scope": "scheduled_recording",
                "scheduled_recording_id": str(pending.id),
            },
            expires_delta=timedelta(hours=1),
        )
        
        return PendingRecordingResponse(
            should_record=True,
            scheduled_recording=ScheduledRecordingOut(
                id=pending.id,
                class_name=pending.class_name,
                teacher_name=pending.teacher_name,
                scheduled_at=pending.scheduled_at.isoformat(),
                timezone=pending.timezone,
                status=pending.status,
                location_name=pending.location_name,
                ai_confidence=pending.ai_confidence,
                created_at=pending.created_at.isoformat()
            ),
            recording_token=recording_token,
            message=f"Iniciando grabación de {pending.class_name}"
        )


@router.get("", response_model=List[ScheduledRecordingOut])
async def list_scheduled_recordings(
    status: Optional[str] = Query(None, description="Filtrar por status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user=Depends(get_current_user)
):
    """Lista las grabaciones programadas del usuario"""
    async with get_primary_session() as session:
        query = select(ScheduledRecording).where(
            ScheduledRecording.user_id == user["user_id"]
        )
        
        if status:
            query = query.where(ScheduledRecording.status == status)
        
        query = query.order_by(desc(ScheduledRecording.scheduled_at)).offset(offset).limit(limit)
        result = await session.execute(query)
        recordings = result.scalars().all()
        
        return [
            ScheduledRecordingOut(
                id=r.id,
                class_name=r.class_name,
                teacher_name=r.teacher_name,
                scheduled_at=r.scheduled_at.isoformat(),
                timezone=r.timezone,
                status=r.status,
                location_name=r.location_name,
                ai_confidence=r.ai_confidence,
                created_at=r.created_at.isoformat()
            )
            for r in recordings
        ]


@router.post("/{recording_id}/cancel")
async def cancel_scheduled_recording(
    recording_id: str,
    user=Depends(get_current_user)
):
    """Cancela una grabación programada"""
    async with get_primary_session() as session:
        recording = await session.get(ScheduledRecording, recording_id)
        
        if not recording or recording.user_id != user["user_id"]:
            raise HTTPException(status_code=404, detail="recording_not_found")
        
        if recording.status not in ["pending", "recording"]:
            raise HTTPException(status_code=400, detail="cannot_cancel_completed_recording")
        
        recording.status = "cancelled"
        recording.cancelled_at = datetime.utcnow()
        await session.commit()
        
        return {"success": True, "message": "Grabación cancelada"}


@router.post("/update-location")
async def update_user_location(
    payload: UpdateLocationRequest,
    device_id: Optional[str] = Header(None),
    platform: Optional[str] = Header(None, description="ios/android"),
    user=Depends(get_current_user)
):
    """
    Actualiza ubicación y contexto del usuario desde la app móvil.
    La app envía esto periódicamente (cada 5 minutos cuando está activa).
    """
    context = await user_context_service.update_location(
        user_id=user["user_id"],
        lat=payload.lat,
        lng=payload.lng,
        device_id=device_id,
        battery_level=payload.battery_level,
        device_platform=platform
    )
    
    return {
        "success": True, 
        "message": "Ubicación actualizada",
        "last_updated": context.location_updated_at.isoformat() if context.location_updated_at else None
    }


# =============================================
# UTILS
# =============================================

def _calculate_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calcula distancia aproximada en metros entre dos puntos.
    Usa fórmula de Haversine simplificada.
    """
    from math import radians, sin, cos, sqrt, atan2
    
    R = 6371000  # Radio de la Tierra en metros
    
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    delta_lat = radians(lat2 - lat1)
    delta_lng = radians(lng2 - lng1)
    
    a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lng / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    
    return R * c
