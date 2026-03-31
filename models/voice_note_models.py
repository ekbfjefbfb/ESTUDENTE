"""
📝 VoiceNote Models - Sistema de Notas SST Puro Offline-First
Características:
- Subida resumible con chunks
- Idempotencia en procesamiento
- Sincronización offline-first
- Procesamiento asíncrono de transcripción
"""
from sqlalchemy import Column, String, Integer, DateTime, Float, Text, Boolean, ForeignKey, JSON, Enum, BigInteger, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import Dict, Any, List, Optional
import enum
import uuid

# Importar User y Base para compartir el mismo registry
from models.models import User, Base

# =============================================
# ENUMS PARA SISTEMA DE NOTAS DE VOZ
# =============================================

class VoiceNoteStatus(str, enum.Enum):
    """Estados del ciclo de vida de una nota de voz"""
    DRAFT = "draft"                    # Creada localmente, no sincronizada
    UPLOADING = "uploading"            # Subiendo chunks
    UPLOADED = "uploaded"              # Audio completo en servidor
    QUEUED = "queued"                  # En cola para transcripción
    TRANSCRIBING = "transcribing"      # Procesando STT
    PROCESSING = "processing"          # Generando resumen/items
    COMPLETED = "completed"            # Todo listo
    ERROR = "error"                    # Fallo en algún paso
    CANCELLED = "cancelled"            # Usuario canceló

class VoiceNoteUploadStrategy(str, enum.Enum):
    """Estrategia de subida usada"""
    STREAMING = "streaming"            # Subida en tiempo real vía WS
    RESUMABLE = "resumable"            # Subida por chunks con resume
    BULK = "bulk"                      # Subida completa de archivo

class AudioChunkStatus(str, enum.Enum):
    """Estado de cada chunk de audio"""
    PENDING = "pending"                # No recibido aún
    RECEIVED = "received"              # Recibido, no verificado
    VERIFIED = "verified"              # Checksum OK
    FAILED = "failed"                  # Error de checksum o corrupto

class ProcessingJobType(str, enum.Enum):
    """Tipo de job de procesamiento en background"""
    TRANSCRIPTION = "transcription"    # STT puro
    SUMMARIZATION = "summarization"    # Resumen del transcript
    EXTRACTION = "extraction"          # Extraer items (tareas, etc)
    FULL_PIPELINE = "full_pipeline"    # Todo el pipeline

class ProcessingJobStatus(str, enum.Enum):
    """Estado de job de procesamiento"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


# =============================================
# MODELO PRINCIPAL: VoiceNote
# =============================================

class VoiceNote(Base):
    """
    🎙️ Nota de voz SST puro - Diseñada para offline-first y resumible
    """
    __tablename__ = "voice_notes"

    # Identificación idempotente
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    
    # Idempotencia: clave única generada cliente-side para evitar duplicados
    # Formato recomendado: "{user_id}:{device_id}:{timestamp}:{random}"
    client_record_id = Column(String(255), unique=True, nullable=False, index=True)
    
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String(100), nullable=False, index=True)  # Para trackear origen
    
    # Metadatos de la grabación
    title = Column(String(200), nullable=True)  # Opcional, AI puede generar
    language = Column(String(10), default="es", nullable=False)
    
    # Estado del ciclo de vida
    status = Column(String(32), default=VoiceNoteStatus.DRAFT, nullable=False, index=True)
    upload_strategy = Column(String(32), default=VoiceNoteUploadStrategy.RESUMABLE)
    
    # Información del audio
    total_duration_ms = Column(Integer, nullable=True)  # Duración total estimada
    total_chunks_expected = Column(Integer, nullable=False)  # Cuántos chunks debería tener
    total_chunks_received = Column(Integer, default=0)
    audio_format = Column(String(20), default="webm")  # webm, mp4, wav, etc
    sample_rate = Column(Integer, nullable=True)  # 16000, 44100, etc
    
    # Tamaño y storage
    total_bytes = Column(BigInteger, nullable=True)  # Tamaño total del audio
    storage_path = Column(String(500), nullable=True)  # Ruta en storage (S3/Local)
    storage_etag = Column(String(255), nullable=True)  # ETag para verificación
    
    # Contenido procesado
    transcript = Column(Text, nullable=True)  # Transcripción completa
    transcript_confidence = Column(Float, nullable=True)  # Confianza promedio STT
    summary = Column(Text, nullable=True)  # Resumen generado
    summary_model = Column(String(50), nullable=True)  # Modelo usado para resumen
    
    # Metadatos enriquecidos
    extracted_items = Column(JSON, default=list)  # [{type, content, confidence}, ...]
    topics = Column(JSON, default=list)  # Temas detectados
    entities = Column(JSON, default=list)  # Entidades nombradas
    
    # Control de versiones para idempotencia de procesamiento
    processing_version = Column(Integer, default=0)  # Incrementa en re-procesos
    processing_checksum = Column(String(64), nullable=True)  # Hash del audio procesado
    
    # Timestamps del ciclo de vida
    recorded_at = Column(DateTime(timezone=True), nullable=False)  # Cuándo grabó el usuario
    client_created_at = Column(DateTime(timezone=True), nullable=False)  # Timestamp del cliente
    upload_started_at = Column(DateTime(timezone=True), nullable=True)
    upload_completed_at = Column(DateTime(timezone=True), nullable=True)
    processing_started_at = Column(DateTime(timezone=True), nullable=True)
    processing_completed_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Soft delete para no perder referencias
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    is_deleted = Column(Boolean, default=False, index=True)
    
    # Relaciones
    user = relationship("User")
    chunks = relationship("VoiceNoteChunk", back_populates="voice_note", cascade="all, delete-orphan", lazy="selectin")
    processing_jobs = relationship("VoiceNoteProcessingJob", back_populates="voice_note", cascade="all, delete-orphan")
    
    # Índices compuestos para queries comunes
    __table_args__ = (
        Index('idx_voice_notes_user_status', 'user_id', 'status'),
        Index('idx_voice_notes_user_created', 'user_id', 'created_at'),
        Index('idx_voice_notes_client_record', 'client_record_id'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialización segura para API"""
        return {
            "id": self.id,
            "client_record_id": self.client_record_id,
            "title": self.title,
            "status": self.status,
            "language": self.language,
            "total_duration_ms": self.total_duration_ms,
            "total_chunks_expected": self.total_chunks_expected,
            "total_chunks_received": self.total_chunks_received,
            "upload_progress_pct": self.upload_progress,
            "transcript_preview": self.transcript[:200] if self.transcript else None,
            "has_summary": bool(self.summary),
            "extracted_items_count": len(self.extracted_items or []),
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
            "upload_completed_at": self.upload_completed_at.isoformat() if self.upload_completed_at else None,
            "processing_completed_at": self.processing_completed_at.isoformat() if self.processing_completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    @property
    def upload_progress(self) -> float:
        """Porcentaje de progreso de subida"""
        if self.total_chunks_expected == 0:
            return 0.0
        return min(100.0, (self.total_chunks_received / self.total_chunks_expected) * 100)
    
    @property
    def is_fully_uploaded(self) -> bool:
        """Verifica si todos los chunks fueron recibidos"""
        return self.total_chunks_received >= self.total_chunks_expected and self.total_chunks_expected > 0
    
    @property
    def can_process(self) -> bool:
        """Verifica si está listo para procesamiento"""
        return (
            self.status in [VoiceNoteStatus.UPLOADED, VoiceNoteStatus.ERROR] 
            and self.is_fully_uploaded 
            and not self.is_deleted
        )


# =============================================
# MODELO: VoiceNoteChunk (Subida Resumible)
# =============================================

class VoiceNoteChunk(Base):
    """
    📦 Chunk de audio para subida resumible
    Cada chunk es verificable y reemplazable (idempotente)
    """
    __tablename__ = "voice_note_chunks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Relación
    voice_note_id = Column(String(36), ForeignKey("voice_notes.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Identificación del chunk
    chunk_index = Column(Integer, nullable=False)  # Posición en secuencia (0-based)
    client_chunk_id = Column(String(255), nullable=False)  # ID generado cliente-side
    
    # Metadatos del chunk
    byte_offset = Column(BigInteger, nullable=False)  # Offset en el archivo final
    byte_length = Column(Integer, nullable=False)  # Tamaño de este chunk
    
    # Verificación de integridad
    checksum_sha256 = Column(String(64), nullable=False)  # Hash del contenido
    status = Column(String(32), default=AudioChunkStatus.PENDING)
    
    # Storage
    storage_path = Column(String(500), nullable=True)
    
    # Timestamps
    received_at = Column(DateTime(timezone=True), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relación
    voice_note = relationship("VoiceNote", back_populates="chunks")
    
    # Índice único compuesto para evitar duplicados de chunk
    __table_args__ = (
        Index('idx_voice_note_chunks_note_index', 'voice_note_id', 'chunk_index', unique=True),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_index": self.chunk_index,
            "byte_offset": self.byte_offset,
            "byte_length": self.byte_length,
            "status": self.status,
            "checksum_sha256": self.checksum_sha256[:16] + "..." if self.checksum_sha256 else None,
            "received_at": self.received_at.isoformat() if self.received_at else None,
        }


# =============================================
# MODELO: VoiceNoteProcessingJob (Jobs Async)
# =============================================

class VoiceNoteProcessingJob(Base):
    """
    ⚙️ Job de procesamiento en background (transcripción, resumen, etc)
    Idempotente: mismo audio + mismo tipo = mismo resultado
    """
    __tablename__ = "voice_note_processing_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Relación
    voice_note_id = Column(String(36), ForeignKey("voice_notes.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Tipo y estado
    job_type = Column(String(32), nullable=False, index=True)
    status = Column(String(32), default=ProcessingJobStatus.PENDING, nullable=False, index=True)
    
    # Idempotencia: clave de determinismo
    # Mismo audio_checksum + job_type + params_hash = job idempotente
    audio_checksum = Column(String(64), nullable=False)  # SHA256 del audio completo
    params_hash = Column(String(64), nullable=False)  # Hash de parámetros del job
    
    # Parámetros y resultado
    job_params = Column(JSON, default=dict)  # {model, language, temperature, etc}
    result_data = Column(JSON, nullable=True)  # Resultado del procesamiento
    error_info = Column(JSON, nullable=True)  # {message, code, stack, retryable}
    
    # Métricas
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)  # Tiempo de procesamiento
    
    # Cola
    queue_name = Column(String(50), default="default")
    priority = Column(Integer, default=0)  # Mayor = más prioritario
    scheduled_at = Column(DateTime(timezone=True), default=func.now())
    
    # Lock para evitar procesamiento concurrente
    worker_id = Column(String(100), nullable=True)  # ID del worker que lo tomó
    locked_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relación
    voice_note = relationship("VoiceNote", back_populates="processing_jobs")
    
    # Índice para buscar jobs idempotentes
    __table_args__ = (
        Index('idx_processing_jobs_idempotent', 'audio_checksum', 'job_type', 'params_hash'),
        Index('idx_processing_jobs_status_queue', 'status', 'queue_name', 'priority'),
    )
    
    @property
    def is_locked(self) -> bool:
        """Verifica si el job está lockeado por un worker"""
        if not self.locked_at:
            return False
        # Lock expira después de 5 minutos sin heartbeat
        lock_age = datetime.utcnow() - self.locked_at
        return lock_age.total_seconds() < 300
    
    @property
    def can_retry(self) -> bool:
        """Verifica si se puede reintentar"""
        return (
            self.status == ProcessingJobStatus.FAILED 
            and self.attempts < self.max_attempts
            and (self.error_info or {}).get("retryable", True)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "job_type": self.job_type,
            "status": self.status,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "can_retry": self.can_retry,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# =============================================
# MODELO: VoiceNoteSyncCheckpoint
# =============================================

class VoiceNoteSyncCheckpoint(Base):
    """
    🔄 Checkpoint de sincronización para offline-first
    Permite al cliente saber qué necesita subir/bajar
    """
    __tablename__ = "voice_note_sync_checkpoints"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String(100), nullable=False, index=True)
    
    # Estado del cliente en su último sync
    client_last_sync_at = Column(DateTime(timezone=True), nullable=False)
    client_record_ids = Column(JSON, default=list)  # IDs que el cliente conoce
    
    # Respuesta del servidor
    server_sync_at = Column(DateTime(timezone=True), server_default=func.now())
    missing_on_server = Column(JSON, default=list)  # IDs que necesita subir
    missing_on_client = Column(JSON, default=list)  # IDs que necesita bajar
    conflicts = Column(JSON, default=list)  # IDs con conflictos de versión
    
    # Metadatos
    sync_duration_ms = Column(Integer, nullable=True)
    records_total = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Índice para queries de sync
    __table_args__ = (
        Index('idx_sync_checkpoints_user_device', 'user_id', 'device_id', 'created_at'),
    )


# =============================================
# EXPORTS
# =============================================

__all__ = [
    "VoiceNoteStatus",
    "VoiceNoteUploadStrategy", 
    "AudioChunkStatus",
    "ProcessingJobType",
    "ProcessingJobStatus",
    "VoiceNote",
    "VoiceNoteChunk",
    "VoiceNoteProcessingJob",
    "VoiceNoteSyncCheckpoint",
]
