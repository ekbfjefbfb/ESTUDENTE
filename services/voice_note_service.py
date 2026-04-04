"""
🎙️ VoiceNoteService - Servicio de Notas SST Puro Offline-First
Features:
- Subida resumible con verificación checksum
- Idempotencia en creación y procesamiento
- Procesamiento asíncrono con jobs
- Sincronización offline-first
"""
import os
import hashlib
import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

from sqlalchemy import select, and_, delete, desc
from sqlalchemy.orm import selectinload

from database.db_enterprise import get_primary_session
from models.voice_note_models import (
    VoiceNote, VoiceNoteChunk, VoiceNoteProcessingJob,
    VoiceNoteStatus, AudioChunkStatus, ProcessingJobType,
    ProcessingJobStatus, VoiceNoteSyncCheckpoint
)

# Configuración
CHUNK_SIZE_BYTES = 256 * 1024  # 256KB por chunk
MAX_RETRIES = 3
STORAGE_DIR = os.environ.get("VOICE_STORAGE_PATH", "./voice_storage")

logger = logging.getLogger("voice_note_service")


class VoiceNoteError(Exception):
    """Error específico del servicio de notas de voz"""
    pass


class ChunkVerificationError(VoiceNoteError):
    """Error de verificación de chunk (checksum mismatch)"""
    pass


class VoiceNoteService:
    """
    Servicio para gestión de notas de voz con soporte offline-first
    """
    
    def __init__(self):
        self.storage_dir = Path(STORAGE_DIR)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"✅ VoiceNoteService inicializado. Storage: {self.storage_dir}")
    
    # =============================================
    # CREACIÓN IDEMPOTENTE
    # =============================================
    
    async def create_voice_note(
        self,
        user_id: str,
        client_record_id: str,
        device_id: str,
        total_duration_ms: Optional[int] = None,
        total_bytes: Optional[int] = None,
        audio_format: str = "webm",
        sample_rate: Optional[int] = None,
        language: str = "es",
        title: Optional[str] = None,
        recorded_at: Optional[datetime] = None,
        client_created_at: Optional[datetime] = None,
    ) -> Tuple[VoiceNote, bool]:
        """
        Crea una nueva VoiceNote de forma idempotente.
        Si client_record_id ya existe, retorna la existente.
        
        Returns:
            (VoiceNote, is_new): La nota y si fue creada nueva
        """
        async with await get_primary_session() as session:
            # Idempotencia: buscar por client_record_id
            existing = await session.execute(
                select(VoiceNote).where(
                    and_(
                        VoiceNote.user_id == user_id,
                        VoiceNote.client_record_id == client_record_id,
                    )
                )
            )
            voice_note = existing.scalar_one_or_none()
            
            if voice_note:
                logger.info(f"🔄 VoiceNote existente encontrada: {voice_note.id} (client_record_id: {client_record_id})")
                return voice_note, False
            
            # Calcular chunks esperados
            chunk_size = CHUNK_SIZE_BYTES
            total_chunks = 1
            if total_bytes:
                total_chunks = max(1, (total_bytes + chunk_size - 1) // chunk_size)
            
            # Crear nueva
            voice_note = VoiceNote(
                user_id=user_id,
                client_record_id=client_record_id,
                device_id=device_id,
                title=title,
                language=language,
                status=VoiceNoteStatus.DRAFT,
                total_duration_ms=total_duration_ms,
                total_bytes=total_bytes,
                total_chunks_expected=total_chunks,
                audio_format=audio_format,
                sample_rate=sample_rate,
                recorded_at=recorded_at or datetime.utcnow(),
                client_created_at=client_created_at or datetime.utcnow(),
            )
            
            session.add(voice_note)
            await session.commit()
            await session.refresh(voice_note)
            
            logger.info(f"📝 VoiceNote creada: {voice_note.id} (chunks esperados: {total_chunks})")
            return voice_note, True
    
    # =============================================
    # SUBIDA RESUMIBLE
    # =============================================
    
    async def upload_chunk(
        self,
        voice_note_id: str,
        chunk_index: int,
        chunk_data: bytes,
        checksum_sha256: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        Recibe un chunk de audio con verificación de integridad.
        Idempotente: mismo chunk_index = reemplazo idempotente.
        """
        async with await get_primary_session() as session:
            # Verificar ownership
            voice_note_result = await session.execute(
                select(VoiceNote)
                .where(
                    and_(
                        VoiceNote.id == voice_note_id,
                        VoiceNote.user_id == user_id,
                    )
                )
                .with_for_update()
            )
            voice_note = voice_note_result.scalar_one_or_none()
            if not voice_note:
                raise VoiceNoteError("voice_note_not_found_or_unauthorized")
            
            # Verificar checksum
            computed_hash = hashlib.sha256(chunk_data).hexdigest()
            if computed_hash != checksum_sha256:
                logger.warning(f"❌ Checksum mismatch en chunk {chunk_index} de {voice_note_id}")
                raise ChunkVerificationError("checksum_mismatch")
            
            # Buscar chunk existente (idempotencia)
            existing_chunk = await session.execute(
                select(VoiceNoteChunk).where(
                    and_(
                        VoiceNoteChunk.voice_note_id == voice_note_id,
                        VoiceNoteChunk.chunk_index == chunk_index
                    )
                )
            )
            chunk = existing_chunk.scalar_one_or_none()
            
            # Calcular offset
            byte_offset = chunk_index * CHUNK_SIZE_BYTES
            
            if chunk:
                # Actualizar existente (re-upload)
                chunk.checksum_sha256 = checksum_sha256
                chunk.byte_length = len(chunk_data)
                chunk.status = AudioChunkStatus.RECEIVED
                chunk.received_at = datetime.utcnow()
                chunk.verified_at = None  # Re-verificar
                is_new_chunk = False
            else:
                # Crear nuevo chunk
                chunk = VoiceNoteChunk(
                    voice_note_id=voice_note_id,
                    chunk_index=chunk_index,
                    client_chunk_id=f"{voice_note_id}:{chunk_index}:{datetime.utcnow().timestamp()}",
                    byte_offset=byte_offset,
                    byte_length=len(chunk_data),
                    checksum_sha256=checksum_sha256,
                    status=AudioChunkStatus.RECEIVED,
                    received_at=datetime.utcnow(),
                )
                session.add(chunk)
                is_new_chunk = True
            
            await session.commit()
            
            # Guardar en storage (async)
            storage_path = await self._save_chunk_to_storage(
                voice_note_id, chunk_index, chunk_data
            )
            chunk.storage_path = storage_path
            chunk.status = AudioChunkStatus.VERIFIED
            chunk.verified_at = datetime.utcnow()
            
            # Actualizar contador
            if is_new_chunk:
                voice_note.total_chunks_received += 1
                if voice_note.upload_started_at is None:
                    voice_note.upload_started_at = datetime.utcnow()
                if voice_note.status == VoiceNoteStatus.DRAFT:
                    voice_note.status = VoiceNoteStatus.UPLOADING
            
            # Verificar si completamos
            is_complete = voice_note.total_chunks_received >= voice_note.total_chunks_expected
            if is_complete:
                voice_note.status = VoiceNoteStatus.UPLOADED
                voice_note.upload_completed_at = datetime.utcnow()
                
                # Calcular checksum total del audio
                await self._calculate_audio_checksum(voice_note)
            
            await session.commit()
            
            logger.info(f"📦 Chunk {chunk_index}/{voice_note.total_chunks_expected} "
                       f"recibido para {voice_note_id} (completo: {is_complete})")
            
            return {
                "chunk_index": chunk_index,
                "status": "received" if not is_complete else "complete",
                "upload_progress_pct": voice_note.upload_progress,
                "is_complete": is_complete,
                "missing_chunks": await self._get_missing_chunks(session, voice_note),
            }
    
    async def _save_chunk_to_storage(
        self, 
        voice_note_id: str, 
        chunk_index: int, 
        data: bytes
    ) -> str:
        """Guarda chunk en filesystem (placeholder para S3)"""
        note_dir = self.storage_dir / voice_note_id
        note_dir.mkdir(exist_ok=True)
        
        chunk_path = note_dir / f"chunk_{chunk_index:05d}.bin"
        
        # Escribir de forma asíncrona
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, 
            lambda: chunk_path.write_bytes(data)
        )
        
        return str(chunk_path)
    
    async def _calculate_audio_checksum(self, voice_note: VoiceNote) -> str:
        """Calcula checksum SHA256 del audio completo (concatenando chunks)"""
        note_dir = self.storage_dir / voice_note.id
        digest = hashlib.sha256()

        if note_dir.exists():
            chunk_files = sorted(note_dir.glob("chunk_*.bin"))
            for chunk_path in chunk_files:
                data = await asyncio.to_thread(chunk_path.read_bytes)
                digest.update(data)
        else:
            digest.update(f"{voice_note.id}:{voice_note.total_chunks_received}".encode())

        voice_note.processing_checksum = digest.hexdigest()
        return voice_note.processing_checksum
    
    async def _get_missing_chunks(
        self, 
        session, 
        voice_note: VoiceNote
    ) -> List[int]:
        """Retorna lista de índices de chunks faltantes"""
        received = await session.execute(
            select(VoiceNoteChunk.chunk_index).where(
                VoiceNoteChunk.voice_note_id == voice_note.id
            )
        )
        received_indices = {r[0] for r in received.all()}
        
        missing = []
        for i in range(voice_note.total_chunks_expected):
            if i not in received_indices:
                missing.append(i)
        
        return missing
    
    async def get_upload_status(
        self, 
        voice_note_id: str, 
        user_id: str
    ) -> Dict[str, Any]:
        """Obtiene estado de subida con chunks faltantes"""
        async with await get_primary_session() as session:
            voice_note = await session.get(VoiceNote, voice_note_id)
            if not voice_note or voice_note.user_id != user_id:
                raise VoiceNoteError("not_found")
            
            missing = await self._get_missing_chunks(session, voice_note)
            
            return {
                "voice_note_id": voice_note_id,
                "status": voice_note.status,
                "upload_progress_pct": voice_note.upload_progress,
                "total_chunks": voice_note.total_chunks_expected,
                "received_chunks": voice_note.total_chunks_received,
                "missing_chunks": missing,
                "missing_count": len(missing),
                "can_resume": len(missing) > 0 and voice_note.status not in [
                    VoiceNoteStatus.COMPLETED, VoiceNoteStatus.CANCELLED
                ],
            }
    
    async def abort_upload(
        self, 
        voice_note_id: str, 
        user_id: str
    ) -> bool:
        """Cancela una subida en progreso y limpia recursos"""
        async with await get_primary_session() as session:
            voice_note = await session.get(VoiceNote, voice_note_id)
            if not voice_note or voice_note.user_id != user_id:
                return False
            
            voice_note.status = VoiceNoteStatus.CANCELLED
            voice_note.is_deleted = True
            voice_note.deleted_at = datetime.utcnow()
            
            # Soft delete de chunks
            await session.execute(
                delete(VoiceNoteChunk).where(
                    VoiceNoteChunk.voice_note_id == voice_note_id
                )
            )
            
            await session.commit()
            
            # Cleanup async de archivos
            from utils.background import safe_create_task
            safe_create_task(self._cleanup_storage(voice_note_id), name="cleanup_storage")
            
            return True
    
    async def _cleanup_storage(self, voice_note_id: str):
        """Limpia archivos de storage"""
        try:
            note_dir = self.storage_dir / voice_note_id
            if note_dir.exists():
                import shutil
                shutil.rmtree(note_dir)
        except Exception as e:
            logger.warning(f"Error limpiando storage para {voice_note_id}: {e}")
    
    # =============================================
    # PROCESAMIENTO ASÍNCRONO (JOBS)
    # =============================================
    
    async def enqueue_processing(
        self,
        voice_note_id: str,
        user_id: str,
        job_type: str = ProcessingJobType.FULL_PIPELINE,
        priority: int = 0,
        job_params: Optional[Dict] = None,
    ) -> VoiceNoteProcessingJob:
        """
        Encola un job de procesamiento de forma idempotente.
        Mismo audio_checksum + job_type + params_hash = mismo job.
        """
        async with await get_primary_session() as session:
            voice_note = await session.get(VoiceNote, voice_note_id)
            if not voice_note or voice_note.user_id != user_id:
                raise VoiceNoteError("not_found")
            
            if not voice_note.can_process:
                raise VoiceNoteError("voice_note_not_ready_for_processing")
            
            # Calcular hashes de idempotencia
            audio_checksum = voice_note.processing_checksum or ""
            params = job_params or {}
            params_hash = hashlib.sha256(
                f"{job_type}:{str(sorted(params.items()))}".encode()
            ).hexdigest()
            
            # Buscar job existente idempotente
            existing = await session.execute(
                select(VoiceNoteProcessingJob).where(
                    and_(
                        VoiceNoteProcessingJob.voice_note_id == voice_note_id,
                        VoiceNoteProcessingJob.audio_checksum == audio_checksum,
                        VoiceNoteProcessingJob.job_type == job_type,
                        VoiceNoteProcessingJob.params_hash == params_hash,
                    )
                )
            )
            job = existing.scalar_one_or_none()
            
            if job:
                # Reutilizar job existente
                if job.status == ProcessingJobStatus.COMPLETED:
                    logger.info(f"🔄 Reutilizando job completado: {job.id}")
                    # Copiar resultado a voice_note
                    await self._apply_job_result(voice_note, job)
                else:
                    logger.info(f"🔄 Job existente encontrado: {job.id} (status: {job.status})")
                
                await session.commit()
                return job
            
            # Crear nuevo job
            job = VoiceNoteProcessingJob(
                voice_note_id=voice_note_id,
                job_type=job_type,
                status=ProcessingJobStatus.PENDING,
                audio_checksum=audio_checksum,
                params_hash=params_hash,
                job_params=params,
                priority=priority,
                max_attempts=MAX_RETRIES,
            )
            
            session.add(job)
            
            # Actualizar estado de voice_note
            voice_note.status = VoiceNoteStatus.QUEUED
            
            await session.commit()
            await session.refresh(job)
            
            logger.info(f"⚙️ Job de procesamiento creado: {job.id} ({job_type})")
            
            # En producción: enviar a cola (Redis/RabbitMQ/Celery)
            # await self._send_to_queue(job)
            
            return job
    
    async def _apply_job_result(
        self, 
        voice_note: VoiceNote, 
        job: VoiceNoteProcessingJob
    ):
        """Aplica el resultado de un job completado a la voice_note"""
        if not job.result_data:
            return
        
        result = job.result_data
        
        if job.job_type == ProcessingJobType.TRANSCRIPTION:
            voice_note.transcript = result.get("transcript", "")
            voice_note.transcript_confidence = result.get("confidence")
        
        elif job.job_type == ProcessingJobType.SUMMARIZATION:
            voice_note.summary = result.get("summary")
            voice_note.summary_model = result.get("model")
        
        elif job.job_type == ProcessingJobType.EXTRACTION:
            voice_note.extracted_items = result.get("items", [])
            voice_note.topics = result.get("topics", [])
            voice_note.entities = result.get("entities", [])
        
        elif job.job_type == ProcessingJobType.FULL_PIPELINE:
            # Aplicar todo
            voice_note.transcript = result.get("transcript", "")
            voice_note.transcript_confidence = result.get("transcript_confidence")
            voice_note.summary = result.get("summary")
            voice_note.summary_model = result.get("summary_model")
            voice_note.extracted_items = result.get("extracted_items", [])
            voice_note.topics = result.get("topics", [])
            voice_note.entities = result.get("entities", [])
    
    async def get_processing_job(
        self, 
        job_id: str, 
        user_id: str
    ) -> Optional[VoiceNoteProcessingJob]:
        """Obtiene estado de un job de procesamiento"""
        async with await get_primary_session() as session:
            job = await session.get(VoiceNoteProcessingJob, job_id)
            if not job:
                return None
            
            # Verificar ownership via voice_note
            voice_note = await session.get(VoiceNote, job.voice_note_id)
            if not voice_note or voice_note.user_id != user_id:
                return None
            
            return job
    
    async def retry_failed_job(
        self, 
        job_id: str, 
        user_id: str
    ) -> Optional[VoiceNoteProcessingJob]:
        """Reintenta un job fallido"""
        async with await get_primary_session() as session:
            job = await session.get(VoiceNoteProcessingJob, job_id)
            if not job:
                return None
            
            voice_note = await session.get(VoiceNote, job.voice_note_id)
            if not voice_note or voice_note.user_id != user_id:
                return None
            
            if not job.can_retry:
                raise VoiceNoteError("job_cannot_be_retried")
            
            job.status = ProcessingJobStatus.PENDING
            job.attempts = 0
            job.error_info = None
            job.locked_at = None
            job.worker_id = None
            
            await session.commit()
            
            return job
    
    # =============================================
    # SINCRONIZACIÓN OFFLINE-FIRST
    # =============================================
    
    async def sync_check(
        self,
        user_id: str,
        device_id: str,
        client_last_sync_at: datetime,
        client_record_ids: List[str],
    ) -> Dict[str, Any]:
        """
        Check de sincronización: qué necesita subir/bajar el cliente
        """
        async with await get_primary_session() as session:
            start_time = datetime.utcnow()
            
            # Obtener todas las voice_notes del usuario
            result = await session.execute(
                select(VoiceNote.client_record_id, VoiceNote.updated_at, VoiceNote.status)
                .where(
                    and_(
                        VoiceNote.user_id == user_id,
                        VoiceNote.is_deleted.is_(False)
                    )
                )
            )
            server_records = {r[0]: {"updated_at": r[1], "status": r[2]} for r in result.all()}
            
            client_set = set(client_record_ids)
            server_set = set(server_records.keys())
            
            # Calcular diferencias
            missing_on_server = list(client_set - server_set)  # Cliente tiene, servidor no
            missing_on_client = list(server_set - client_set)  # Servidor tiene, cliente no
            
            # Conflictos: ambos tienen pero diferente timestamp
            conflicts = []
            for record_id in client_set & server_set:
                server_updated = server_records[record_id]["updated_at"]
                # En producción: comparar con timestamp del cliente
                # Simplificación: si servidor es más reciente, posible conflicto
                if server_updated and server_updated > client_last_sync_at:
                    conflicts.append(record_id)
            
            # Detalles de los que necesita bajar el cliente
            need_download_details = []
            if missing_on_client:
                details_result = await session.execute(
                    select(VoiceNote)
                    .options(selectinload(VoiceNote.chunks))
                    .where(
                        and_(
                            VoiceNote.user_id == user_id,
                            VoiceNote.client_record_id.in_(missing_on_client[:50]),  # Limit
                            VoiceNote.is_deleted.is_(False)
                        )
                    )
                )
                need_download_details = [v.to_dict() for v in details_result.scalars().all()]
            
            # Crear checkpoint
            checkpoint = VoiceNoteSyncCheckpoint(
                user_id=user_id,
                device_id=device_id,
                client_last_sync_at=client_last_sync_at,
                client_record_ids=client_record_ids,
                missing_on_server=missing_on_server,
                missing_on_client=missing_on_client,
                conflicts=conflicts,
                records_total=len(server_records),
            )
            session.add(checkpoint)
            
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            checkpoint.sync_duration_ms = duration_ms
            
            await session.commit()
            
            return {
                "checkpoint_id": checkpoint.id,
                "server_sync_at": datetime.utcnow().isoformat(),
                "missing_on_server_count": len(missing_on_server),
                "missing_on_server": missing_on_server,
                "missing_on_client_count": len(missing_on_client),
                "missing_on_client": missing_on_client[:100],  # Limit
                "conflicts_count": len(conflicts),
                "conflicts": conflicts,
                "server_records_total": len(server_records),
                "details_to_download": need_download_details,
                "sync_duration_ms": duration_ms,
            }
    
    # =============================================
    # CONSULTAS
    # =============================================
    
    async def list_voice_notes(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> Dict[str, Any]:
        """Lista notas de voz del usuario"""
        async with await get_primary_session() as session:
            filters = [VoiceNote.user_id == user_id]
            
            if not include_deleted:
                filters.append(VoiceNote.is_deleted.is_(False))
            
            if status:
                filters.append(VoiceNote.status == status)

            query = select(VoiceNote).where(*filters)
            
            # Ordenar por recorded_at desc
            query = query.order_by(desc(VoiceNote.recorded_at))
            
            # Aplicar paginación
            query = query.offset(offset).limit(limit)
            
            result = await session.execute(
                query.options(selectinload(VoiceNote.processing_jobs))
            )
            notes = result.scalars().all()
            
            # Contar total
            count_result = await session.execute(
                select(VoiceNote.id).where(*filters)
            )
            total = len(count_result.scalars().all())
            
            return {
                "notes": [n.to_dict() for n in notes],
                "total": total,
                "limit": limit,
                "offset": offset,
            }
    
    async def get_voice_note(
        self, 
        voice_note_id: str, 
        user_id: str
    ) -> Optional[VoiceNote]:
        """Obtiene detalle completo de una nota"""
        async with await get_primary_session() as session:
            result = await session.execute(
                select(VoiceNote)
                .options(
                    selectinload(VoiceNote.chunks),
                    selectinload(VoiceNote.processing_jobs)
                )
                .where(
                    and_(
                        VoiceNote.id == voice_note_id,
                        VoiceNote.user_id == user_id,
                        VoiceNote.is_deleted.is_(False)
                    )
                )
            )
            return result.scalar_one_or_none()
    
    async def delete_voice_note(
        self, 
        voice_note_id: str, 
        user_id: str,
        hard_delete: bool = False,
    ) -> bool:
        """Elimina una nota (soft o hard delete)"""
        async with await get_primary_session() as session:
            voice_note = await session.get(VoiceNote, voice_note_id)
            if not voice_note or voice_note.user_id != user_id:
                return False
            
            if hard_delete:
                await session.delete(voice_note)
            else:
                voice_note.is_deleted = True
                voice_note.deleted_at = datetime.utcnow()
            
            await session.commit()
            
            # Cleanup async
            if hard_delete:
                from utils.background import safe_create_task
                safe_create_task(self._cleanup_storage(voice_note_id), name="cleanup_storage_delete")
            
            return True
    
    async def update_voice_note(
        self,
        voice_note_id: str,
        user_id: str,
        title: Optional[str] = None,
    ) -> Optional[VoiceNote]:
        """Actualiza metadatos de una nota"""
        async with await get_primary_session() as session:
            voice_note = await session.get(VoiceNote, voice_note_id)
            if not voice_note or voice_note.user_id != user_id:
                return None
            
            if title is not None:
                voice_note.title = title
            
            await session.commit()
            await session.refresh(voice_note)
            
            return voice_note


# Singleton
voice_note_service = VoiceNoteService()
