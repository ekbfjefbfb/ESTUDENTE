"""
🎙️ VoiceNote Router - API REST para Notas SST Puro Offline-First
Endpoints:
- Creación idempotente de notas
- Subida resumible por chunks
- Consulta de estado
- Sincronización offline-first
- Procesamiento asíncrono
"""
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from services.voice_note_service import (
    voice_note_service, 
    VoiceNoteError, 
    ChunkVerificationError,
    CHUNK_SIZE_BYTES
)
from models.voice_note_models import (
    ProcessingJobType
)

logger = logging.getLogger("voice_note_router")

router = APIRouter(prefix="/api/voice-notes", tags=["Voice Notes"])


def _request_base_url(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}".rstrip("/")
    return str(request.base_url).rstrip("/")


# =============================================
# MODELOS Pydantic
# =============================================

class CreateVoiceNoteRequest(BaseModel):
    """Request para crear nota de voz (idempotente)"""
    client_record_id: str = Field(
        ..., 
        min_length=10, 
        max_length=255,
        description="ID único generado cliente-side: {user_id}:{device_id}:{timestamp}:{random}"
    )
    device_id: str = Field(..., min_length=1, max_length=100)
    total_duration_ms: Optional[int] = Field(None, ge=0)
    total_bytes: Optional[int] = Field(None, ge=0)
    audio_format: str = Field(default="webm", pattern="^(webm|mp4|wav|m4a|aac)$")
    sample_rate: Optional[int] = Field(None, ge=8000, le=48000)
    language: str = Field(default="es", pattern="^(es|en|pt|fr|de|it)$")
    title: Optional[str] = Field(None, max_length=200)
    recorded_at: Optional[datetime] = None
    client_created_at: Optional[datetime] = None


class UploadChunkRequest(BaseModel):
    """Request para subir chunk de audio"""
    chunk_index: int = Field(..., ge=0)
    chunk_data: str = Field(
        ..., 
        description="Base64 encoded audio chunk"
    )
    checksum_sha256: str = Field(
        ..., 
        min_length=64, 
        max_length=64,
        pattern="^[a-f0-9]{64}$",
        description="SHA256 hash del chunk (hex)"
    )


class UploadChunkResponse(BaseModel):
    """Response de subida de chunk"""
    chunk_index: int
    status: str
    upload_progress_pct: float
    is_complete: bool
    missing_chunks: List[int]


class VoiceNoteOut(BaseModel):
    """Output de VoiceNote para API"""
    id: str
    client_record_id: str
    title: Optional[str]
    status: str
    language: str
    total_duration_ms: Optional[int]
    total_chunks_expected: int
    total_chunks_received: int
    upload_progress_pct: float
    transcript_preview: Optional[str]
    has_summary: bool
    extracted_items_count: int
    recorded_at: Optional[datetime]
    upload_completed_at: Optional[datetime]
    processing_completed_at: Optional[datetime]
    created_at: Optional[datetime]


class ListVoiceNotesResponse(BaseModel):
    """Response de lista de notas"""
    notes: List[VoiceNoteOut]
    total: int
    limit: int
    offset: int


class UploadStatusResponse(BaseModel):
    """Estado de subida con chunks faltantes"""
    voice_note_id: str
    status: str
    upload_progress_pct: float
    total_chunks: int
    received_chunks: int
    missing_chunks: List[int]
    missing_count: int
    can_resume: bool


class SyncCheckRequest(BaseModel):
    """Request para check de sincronización"""
    device_id: str = Field(..., min_length=1, max_length=100)
    client_last_sync_at: datetime
    client_record_ids: List[str] = Field(default_factory=list)


class SyncCheckResponse(BaseModel):
    """Response de check de sincronización"""
    checkpoint_id: str
    server_sync_at: str
    missing_on_server_count: int
    missing_on_server: List[str]
    missing_on_client_count: int
    missing_on_client: List[str]
    conflicts_count: int
    conflicts: List[str]
    server_records_total: int
    details_to_download: List[dict]
    sync_duration_ms: int


class EnqueueProcessingRequest(BaseModel):
    """Request para encolar procesamiento"""
    job_type: str = Field(
        default=ProcessingJobType.FULL_PIPELINE,
        pattern="^(transcription|summarization|extraction|full_pipeline)$"
    )
    priority: int = Field(default=0, ge=0, le=100)
    job_params: Optional[dict] = Field(default_factory=dict)


class ProcessingJobOut(BaseModel):
    """Output de job de procesamiento"""
    id: str
    job_type: str
    status: str
    attempts: int
    max_attempts: int
    can_retry: bool
    duration_ms: Optional[int]
    created_at: Optional[datetime]
    scheduled_at: Optional[datetime]
    completed_at: Optional[datetime]


class VoiceNoteDetailOut(VoiceNoteOut):
    """Output detallado incluyendo chunks y jobs"""
    chunks: List[dict]
    processing_jobs: List[ProcessingJobOut]


class ResumeUploadInfo(BaseModel):
    """Info para resumir una subida"""
    voice_note_id: str
    chunk_size_bytes: int
    total_chunks: int
    missing_chunks: List[int]
    upload_url_template: str  # /api/voice-notes/{id}/chunks


# =============================================
# ENDPOINTS
# =============================================

@router.post("/create", response_model=VoiceNoteOut)
async def create_voice_note(
    payload: CreateVoiceNoteRequest,
    user=Depends(get_current_user)
):
    """
    📝 Crea una VoiceNote de forma idempotente.
    
    Si `client_record_id` ya existe, retorna la existente (no duplica).
    Usa esto para evitar duplicados cuando el cliente sync offline-first.
    """
    try:
        voice_note, is_new = await voice_note_service.create_voice_note(
            user_id=user["user_id"],
            client_record_id=payload.client_record_id,
            device_id=payload.device_id,
            total_duration_ms=payload.total_duration_ms,
            total_bytes=payload.total_bytes,
            audio_format=payload.audio_format,
            sample_rate=payload.sample_rate,
            language=payload.language,
            title=payload.title,
            recorded_at=payload.recorded_at,
            client_created_at=payload.client_created_at,
        )
        
        return voice_note.to_dict()
        
    except Exception as e:
        logger.error(f"Error creando VoiceNote: {e}")
        raise HTTPException(status_code=500, detail="internal_error")


@router.post("/{voice_note_id}/chunks", response_model=UploadChunkResponse)
async def upload_chunk(
    voice_note_id: str,
    payload: UploadChunkRequest,
    user=Depends(get_current_user)
):
    """
    📦 Sube un chunk de audio.
    
    - Verifica checksum SHA256 para integridad
    - Idempotente: re-subir mismo chunk_index = reemplazo
    - Retorna missing_chunks para saber qué falta
    """
    import base64
    
    try:
        # Decode base64
        try:
            chunk_bytes = base64.b64decode(payload.chunk_data)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid_base64_data")
        
        result = await voice_note_service.upload_chunk(
            voice_note_id=voice_note_id,
            chunk_index=payload.chunk_index,
            chunk_data=chunk_bytes,
            checksum_sha256=payload.checksum_sha256,
            user_id=user["user_id"],
        )
        
        return UploadChunkResponse(**result)
        
    except ChunkVerificationError:
        raise HTTPException(status_code=400, detail="checksum_mismatch")
    except VoiceNoteError as e:
        if "not_found" in str(e):
            raise HTTPException(status_code=404, detail="voice_note_not_found")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error subiendo chunk: {e}")
        raise HTTPException(status_code=500, detail="upload_failed")


@router.get("/{voice_note_id}/upload-status", response_model=ResumeUploadInfo)
async def get_upload_status(
    voice_note_id: str,
    request: Request,
    user=Depends(get_current_user)
):
    """
    📊 Obtiene estado de subida para resumir.
    
    Retorna lista de missing_chunks para que el cliente sepa qué subir.
    """
    try:
        status = await voice_note_service.get_upload_status(
            voice_note_id=voice_note_id,
            user_id=user["user_id"],
        )
        
        return ResumeUploadInfo(
            voice_note_id=voice_note_id,
            chunk_size_bytes=CHUNK_SIZE_BYTES,
            total_chunks=status["total_chunks"],
            missing_chunks=status["missing_chunks"],
            upload_url_template=f"{_request_base_url(request)}/api/voice-notes/{voice_note_id}/chunks"
        )
        
    except VoiceNoteError as e:
        if "not_found" in str(e):
            raise HTTPException(status_code=404, detail="voice_note_not_found")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{voice_note_id}/abort")
async def abort_upload(
    voice_note_id: str,
    user=Depends(get_current_user)
):
    """
    ❌ Cancela una subida en progreso.
    
    Soft-delete de la nota y limpieza de recursos.
    """
    success = await voice_note_service.abort_upload(
        voice_note_id=voice_note_id,
        user_id=user["user_id"],
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="voice_note_not_found")
    
    return {"status": "cancelled", "voice_note_id": voice_note_id}


@router.post("/{voice_note_id}/process", response_model=ProcessingJobOut)
async def enqueue_processing(
    voice_note_id: str,
    payload: EnqueueProcessingRequest,
    user=Depends(get_current_user)
):
    """
    ⚙️ Encola procesamiento asíncrono (STT, resumen, etc).
    
    Idempotente: mismo audio + job_type = mismo job reutilizado si existe.
    """
    try:
        job = await voice_note_service.enqueue_processing(
            voice_note_id=voice_note_id,
            user_id=user["user_id"],
            job_type=payload.job_type,
            priority=payload.priority,
            job_params=payload.job_params,
        )
        
        return ProcessingJobOut(**job.to_dict())
        
    except VoiceNoteError as e:
        if "not_found" in str(e):
            raise HTTPException(status_code=404, detail="voice_note_not_found")
        if "not_ready" in str(e):
            raise HTTPException(status_code=400, detail="upload_not_complete")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error encolando procesamiento: {e}")
        raise HTTPException(status_code=500, detail="enqueue_failed")


@router.get("/{voice_note_id}/jobs/{job_id}", response_model=ProcessingJobOut)
async def get_processing_job(
    voice_note_id: str,
    job_id: str,
    user=Depends(get_current_user)
):
    """
    📋 Obtiene estado de un job de procesamiento.
    """
    job = await voice_note_service.get_processing_job(
        job_id=job_id,
        user_id=user["user_id"],
    )
    
    if not job:
        raise HTTPException(status_code=404, detail="job_not_found")
    
    return ProcessingJobOut(**job.to_dict())


@router.post("/{voice_note_id}/jobs/{job_id}/retry", response_model=ProcessingJobOut)
async def retry_job(
    voice_note_id: str,
    job_id: str,
    user=Depends(get_current_user)
):
    """
    🔄 Reintenta un job fallido.
    """
    try:
        job = await voice_note_service.retry_failed_job(
            job_id=job_id,
            user_id=user["user_id"],
        )
        
        if not job:
            raise HTTPException(status_code=404, detail="job_not_found")
        
        return ProcessingJobOut(**job.to_dict())
        
    except VoiceNoteError as e:
        if "cannot_retry" in str(e):
            raise HTTPException(status_code=400, detail="job_cannot_be_retried")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sync-check", response_model=SyncCheckResponse)
async def sync_check(
    payload: SyncCheckRequest,
    user=Depends(get_current_user)
):
    """
    🔄 Check de sincronización offline-first.
    
    El cliente envía sus IDs conocidos, el servidor responde:
    - missing_on_server: IDs que el cliente debe subir
    - missing_on_client: IDs que el cliente debe bajar  
    - conflicts: IDs con posibles conflictos
    """
    result = await voice_note_service.sync_check(
        user_id=user["user_id"],
        device_id=payload.device_id,
        client_last_sync_at=payload.client_last_sync_at,
        client_record_ids=payload.client_record_ids,
    )
    
    return SyncCheckResponse(**result)


@router.get("", response_model=ListVoiceNotesResponse)
async def list_voice_notes(
    status: Optional[str] = Query(None, pattern="^(draft|uploading|uploaded|queued|transcribing|processing|completed|error|cancelled)$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_deleted: bool = Query(default=False),
    user=Depends(get_current_user)
):
    """
    📋 Lista notas de voz del usuario.
    
    - Filtrable por status
    - Paginado
    - Ordenado por recorded_at desc
    """
    result = await voice_note_service.list_voice_notes(
        user_id=user["user_id"],
        status=status,
        limit=limit,
        offset=offset,
        include_deleted=include_deleted,
    )
    
    return ListVoiceNotesResponse(
        notes=[VoiceNoteOut(**n) for n in result["notes"]],
        total=result["total"],
        limit=result["limit"],
        offset=result["offset"],
    )


@router.get("/{voice_note_id}", response_model=VoiceNoteDetailOut)
async def get_voice_note(
    voice_note_id: str,
    user=Depends(get_current_user)
):
    """
    📄 Obtiene detalle completo de una nota incluyendo chunks y jobs.
    """
    voice_note = await voice_note_service.get_voice_note(
        voice_note_id=voice_note_id,
        user_id=user["user_id"],
    )
    
    if not voice_note:
        raise HTTPException(status_code=404, detail="voice_note_not_found")
    
    base_dict = voice_note.to_dict()
    base_dict["chunks"] = [c.to_dict() for c in voice_note.chunks]
    base_dict["processing_jobs"] = [
        ProcessingJobOut(**j.to_dict()).model_dump() 
        for j in voice_note.processing_jobs
    ]
    
    return VoiceNoteDetailOut(**base_dict)


@router.delete("/{voice_note_id}")
async def delete_voice_note(
    voice_note_id: str,
    hard: bool = Query(default=False, description="Eliminar permanentemente"),
    user=Depends(get_current_user)
):
    """
    🗑️ Elimina una nota (soft delete por defecto).
    """
    success = await voice_note_service.delete_voice_note(
        voice_note_id=voice_note_id,
        user_id=user["user_id"],
        hard_delete=hard,
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="voice_note_not_found")
    
    return {
        "status": "deleted" if not hard else "hard_deleted",
        "voice_note_id": voice_note_id
    }


@router.patch("/{voice_note_id}", response_model=VoiceNoteOut)
async def update_voice_note(
    voice_note_id: str,
    title: Optional[str] = Query(None, max_length=200),
    user=Depends(get_current_user)
):
    """
    ✏️ Actualiza metadatos de una nota.
    """
    voice_note = await voice_note_service.update_voice_note(
        voice_note_id=voice_note_id,
        user_id=user["user_id"],
        title=title,
    )
    
    if not voice_note:
        raise HTTPException(status_code=404, detail="voice_note_not_found")
    
    return VoiceNoteOut(**voice_note.to_dict())


# =============================================
# ENDPOINTS DE UTILIDAD
# =============================================

@router.get("/config/upload-params")
async def get_upload_config(request: Request, user=Depends(get_current_user)):
    """
    ⚙️ Retorna configuración de subida para el cliente.
    
    - chunk_size_bytes: tamaño óptimo de cada chunk
    - max_chunks: límite máximo
    - supported_formats: formatos soportados
    """
    return {
        "chunk_size_bytes": CHUNK_SIZE_BYTES,
        "max_chunks": 10000,  # ~2.5GB máximo
        "max_file_size_bytes": 2 * 1024 * 1024 * 1024,  # 2GB
        "supported_formats": ["webm", "mp4", "wav", "m4a", "aac"],
        "recommended_format": "webm",
        "checksum_algorithm": "sha256",
        "create_url": f"{_request_base_url(request)}/api/voice-notes/create",
        "chunk_url_template": f"{_request_base_url(request)}/api/voice-notes/{{voice_note_id}}/chunks",
        "status_url_template": f"{_request_base_url(request)}/api/voice-notes/{{voice_note_id}}/upload-status",
        "process_url_template": f"{_request_base_url(request)}/api/voice-notes/{{voice_note_id}}/process",
    }
