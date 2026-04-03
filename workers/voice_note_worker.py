"""
⚙️ VoiceNote Worker - Procesador de jobs de transcripción/resumen
Ejecuta en background procesamiento de notas de voz.
Ejecutar: python -m workers.voice_note_worker
"""
import os
import sys
import json
import asyncio
import logging
import signal
from datetime import datetime, timedelta
from typing import Optional

# Añadir root al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from database.db_enterprise import get_primary_session
from models.models import User  # Importar User para registrar el mapper en SQLAlchemy
from models.voice_note_models import (
    VoiceNote, 
    VoiceNoteProcessingJob, 
    VoiceNoteChunk,
    ProcessingJobStatus,
    ProcessingJobType,
    VoiceNoteStatus
)

# Servicios opcionales (graceful degradation)
try:
    from services.groq_voice_service import transcribe_audio_groq
    TRANSCRIPTION_AVAILABLE = True
except ImportError:
    TRANSCRIPTION_AVAILABLE = False

try:
    from services.groq_ai_service import chat_with_ai
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("voice_note_worker")

# Config
WORKER_ID = os.environ.get("HOSTNAME", "worker-1")
POLL_INTERVAL_SECONDS = float(os.environ.get("WORKER_POLL_INTERVAL", "5"))
JOB_TIMEOUT_SECONDS = int(os.environ.get("WORKER_JOB_TIMEOUT", "300"))
MAX_CONCURRENT_JOBS = int(os.environ.get("WORKER_MAX_JOBS", "2"))

# Semáforo para limitar concurrencio
_job_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

# Flag para graceful shutdown
_shutdown_event = asyncio.Event()


async def acquire_job(session) -> Optional[VoiceNoteProcessingJob]:
    """
    Adquiere un job pendiente atomáticamente.
    
    Criteria:
    - Status PENDING o RETRYING
    - scheduled_at <= now
    - No lock activo (locked_at > 5 min ago o null)
    """
    five_min_ago = datetime.utcnow() - timedelta(minutes=5)

    result = await session.execute(
        select(VoiceNoteProcessingJob)
        .where(
            VoiceNoteProcessingJob.status.in_(
                [
                    ProcessingJobStatus.PENDING.value,
                    ProcessingJobStatus.RETRYING.value,
                ]
            ),
            VoiceNoteProcessingJob.scheduled_at <= datetime.utcnow(),
            or_(
                VoiceNoteProcessingJob.locked_at.is_(None),
                VoiceNoteProcessingJob.locked_at < five_min_ago,
            ),
        )
        .order_by(VoiceNoteProcessingJob.priority.desc(), VoiceNoteProcessingJob.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = result.scalar_one_or_none()
    if job is None:
        return None

    job.worker_id = WORKER_ID
    job.locked_at = datetime.utcnow()
    job.status = ProcessingJobStatus.RUNNING.value
    job.attempts = int(job.attempts or 0) + 1
    job.started_at = datetime.utcnow()

    await session.commit()
    await session.refresh(job)
    return job


async def get_audio_bytes(voice_note: VoiceNote) -> Optional[bytes]:
    """Reconstruye el audio completo de los chunks"""
    from pathlib import Path
    
    chunks_dir = Path(f"./voice_storage/{voice_note.id}")
    if not chunks_dir.exists():
        return None
    
    # Ordenar chunks por índice
    chunk_files = sorted(chunks_dir.glob("chunk_*.bin"))
    
    audio_buffer = bytearray()
    for chunk_file in chunk_files:
        audio_buffer.extend(chunk_file.read_bytes())
    
    return bytes(audio_buffer)


async def process_transcription_job(
    job: VoiceNoteProcessingJob,
    voice_note: VoiceNote
) -> dict:
    """Procesa job de transcripción STT"""
    
    if not TRANSCRIPTION_AVAILABLE:
        return {
            "success": False,
            "error": "transcription_service_unavailable",
            "transcript": "",
            "confidence": 0.0
        }
    
    try:
        # Reconstruir audio
        audio_bytes = await get_audio_bytes(voice_note)
        if not audio_bytes:
            raise ValueError("audio_not_available")
        
        # Transcribir
        transcript = await transcribe_audio_groq(
            audio_bytes=audio_bytes,
            language=voice_note.language
        )
        
        return {
            "success": True,
            "transcript": transcript or "",
            "confidence": 0.85,  # Placeholder, STT debería retornar confianza
        }
        
    except Exception as e:
        logger.error(f"Error en transcripción: {e}")
        return {
            "success": False,
            "error": str(e),
            "transcript": "",
            "confidence": 0.0
        }


async def process_summarization_job(
    job: VoiceNoteProcessingJob,
    voice_note: VoiceNote
) -> dict:
    """Procesa job de generación de resumen usando Agentes"""
    
    if not AI_AVAILABLE:
        return {"success": False, "error": "ai_service_unavailable"}
    
    try:
        transcript = voice_note.transcript or ""
        if not transcript.strip():
            return {"success": False, "error": "no_transcript_available"}
        
        from services.agent_service import agent_manager
        
        task_desc = f"""
        Resume esta transcripción de nota de voz.
        Identifica los puntos clave y organiza la información de forma ejecutiva.
        
        Transcripción:
        {transcript[:10000]}
        """
        
        logger.info(f"voice_worker: Resumen Agéntico iniciado para {voice_note.id}")
        result = await agent_manager.run_complex_task(task_desc, user_id=voice_note.user_id)
        
        return {
            "success": True,
            "summary": agent_manager.extract_text(result) or "Resumen generado.",
            "model": "agentic_team_v9"
        }
        
    except Exception as e:
        logger.error(f"Error en summarization agéntica: {e}")
        return {"success": False, "error": str(e)}


async def process_extraction_job(
    job: VoiceNoteProcessingJob,
    voice_note: VoiceNote
) -> dict:
    """Procesa job de extracción de items usando Agentes"""
    
    try:
        from services.agent_service import agent_manager
        transcript = voice_note.transcript or ""
        
        task_desc = f"""
        Analiza esta transcripción y extrae:
        1. Items de acción (tareas, recordatorios, deadlines)
        2. Temas principales
        3. Entidades (personas, lugares)
        
        Responde exclusivamente en JSON válido:
        {{
            "items": [{{"type": "task|reminder|deadline", "content": "...", "due_date": "ISO or null"}}],
            "topics": ["tema1", "tema2"],
            "entities": [{{"name": "...", "type": "person|place|org"}}]
        }}
        
        Transcripción:
        {transcript[:10000]}
        """
        
        logger.info(f"voice_worker: Extracción Agéntica iniciada para {voice_note.id}")
        result = await agent_manager.run_complex_task(task_desc, user_id=voice_note.user_id)
        
        # Parsear el JSON de la respuesta del agente
        try:
            import json
            import re
            # Limpiar posibles bloques markdown
            clean_content = re.sub(
                r"```json|```",
                "",
                agent_manager.extract_text(result),
            ).strip()
            data = json.loads(clean_content)
            
            return {
                "success": True,
                "items": data.get("items", []),
                "topics": data.get("topics", []),
                "entities": data.get("entities", []),
            }
        except Exception as parse_e:
            logger.error(f"Error parseando JSON agéntico: {parse_e}")
            return {"success": False, "error": "agentic_json_parse_error"}
            
    except Exception as e:
        logger.error(f"Error en extracción agéntica: {e}")
        return {"success": False, "error": str(e)}


async def process_full_pipeline_job(
    job: VoiceNoteProcessingJob,
    voice_note: VoiceNote
) -> dict:
    """Procesa job completo: transcription + summarization + extraction"""
    
    results = {
        "transcript": "",
        "transcript_confidence": 0.0,
        "summary": None,
        "summary_model": None,
        "extracted_items": [],
        "topics": [],
        "entities": [],
        "stages_completed": []
    }
    
    # 1. Transcripción
    trans_result = await process_transcription_job(job, voice_note)
    if trans_result["success"]:
        results["transcript"] = trans_result["transcript"]
        results["transcript_confidence"] = trans_result["confidence"]
        results["stages_completed"].append("transcription")
        
        # Actualizar voice_note para que siguientes etapas tengan acceso
        voice_note.transcript = results["transcript"]
        voice_note.transcript_confidence = results["transcript_confidence"]
    else:
        results["error"] = f"transcription_failed: {trans_result.get('error')}"
        return results
    
    # 2. Summarization
    summary_result = await process_summarization_job(job, voice_note)
    if summary_result["success"]:
        results["summary"] = summary_result["summary"]
        results["summary_model"] = summary_result["model"]
        results["stages_completed"].append("summarization")
    
    # 3. Extraction
    extract_result = await process_extraction_job(job, voice_note)
    if extract_result["success"]:
        results["extracted_items"] = extract_result["items"]
        results["topics"] = extract_result["topics"]
        results["entities"] = extract_result["entities"]
        results["stages_completed"].append("extraction")
    
    results["success"] = len(results["stages_completed"]) > 0
    return results


async def execute_job(job: VoiceNoteProcessingJob) -> dict:
    """Ejecuta un job según su tipo"""
    
    async with await get_primary_session() as session:
        # Cargar voice_note con chunks
        voice_note = await session.execute(
            select(VoiceNote)
            .options(selectinload(VoiceNote.chunks))
            .where(VoiceNote.id == job.voice_note_id)
        )
        voice_note = voice_note.scalar_one()
        
        job_type = job.job_type
        
        if job_type == ProcessingJobType.TRANSCRIPTION.value:
            result = await process_transcription_job(job, voice_note)
        elif job_type == ProcessingJobType.SUMMARIZATION.value:
            result = await process_summarization_job(job, voice_note)
        elif job_type == ProcessingJobType.EXTRACTION.value:
            result = await process_extraction_job(job, voice_note)
        elif job_type == ProcessingJobType.FULL_PIPELINE.value:
            result = await process_full_pipeline_job(job, voice_note)
        else:
            result = {"success": False, "error": f"unknown_job_type: {job_type}"}
        
        return result


async def handle_job_completion(
    job: VoiceNoteProcessingJob,
    result: dict,
    session
):
    """Maneja la finalización de un job"""
    
    duration_ms = int((datetime.utcnow() - job.started_at).total_seconds() * 1000)
    job.duration_ms = duration_ms
    
    if result.get("success"):
        job.status = ProcessingJobStatus.COMPLETED.value  # Usar .value
        job.result_data = result
        job.completed_at = datetime.utcnow()
        
        # Actualizar voice_note con resultados
        voice_note = await session.get(VoiceNote, job.voice_note_id)
        if voice_note:
            # Aplicar resultados según tipo
            if job.job_type == ProcessingJobType.TRANSCRIPTION.value:
                voice_note.transcript = result.get("transcript", "")
                voice_note.transcript_confidence = result.get("confidence")
                voice_note.status = VoiceNoteStatus.UPLOADED.value  # Usar .value
                voice_note.processing_completed_at = datetime.utcnow()
                
            elif job.job_type == ProcessingJobType.SUMMARIZATION.value:
                voice_note.summary = result.get("summary")
                voice_note.summary_model = result.get("model")
                voice_note.processing_completed_at = datetime.utcnow()
                
            elif job.job_type == ProcessingJobType.EXTRACTION.value:
                voice_note.extracted_items = result.get("items", [])
                voice_note.topics = result.get("topics", [])
                voice_note.entities = result.get("entities", [])
                voice_note.processing_completed_at = datetime.utcnow()
                
            elif job.job_type == ProcessingJobType.FULL_PIPELINE.value:
                voice_note.transcript = result.get("transcript", "")
                voice_note.transcript_confidence = result.get("transcript_confidence")
                voice_note.summary = result.get("summary")
                voice_note.summary_model = result.get("summary_model")
                voice_note.extracted_items = result.get("extracted_items", [])
                voice_note.topics = result.get("topics", [])
                voice_note.entities = result.get("entities", [])
                voice_note.status = VoiceNoteStatus.COMPLETED.value  # Usar .value
                voice_note.processing_completed_at = datetime.utcnow()
                voice_note.processing_version += 1
        
        logger.info(f"✅ Job completado: {job.id} ({job.job_type}) en {duration_ms}ms")
        
    else:
        # Fallo
        error_info = {
            "message": result.get("error", "unknown_error"),
            "code": result.get("error_code", "unknown"),
            "retryable": result.get("retryable", True),
            "stage": result.get("stage"),
        }
        
        job.error_info = error_info
        
        if job.attempts < job.max_attempts and error_info["retryable"]:
            job.status = ProcessingJobStatus.RETRYING.value  # Usar .value
            # Schedule retry con backoff exponencial
            backoff_minutes = 2 ** job.attempts
            job.scheduled_at = datetime.utcnow() + timedelta(minutes=backoff_minutes)
            logger.warning(f"⚠️ Job {job.id} reintentará en {backoff_minutes}min (attempt {job.attempts})")
        else:
            job.status = ProcessingJobStatus.FAILED.value  # Usar .value
            # Actualizar voice_note status
            voice_note = await session.get(VoiceNote, job.voice_note_id)
            if voice_note:
                voice_note.status = VoiceNoteStatus.ERROR.value  # Usar .value
            logger.error(f"❌ Job fallido: {job.id} ({job.job_type}): {error_info['message']}")
    
    # Liberar lock
    job.locked_at = None
    job.worker_id = None
    
    await session.commit()


async def process_single_job():
    """Procesa un solo job si hay disponible"""
    
    async with _job_semaphore:
        session = await get_primary_session()
        async with session:
            job = await acquire_job(session)
            
            if not job:
                return False  # No jobs available
            
            logger.info(f"🔧 Procesando job: {job.id} ({job.job_type}, attempt {job.attempts})")
            
            try:
                # Ejecutar con timeout
                result = await asyncio.wait_for(
                    execute_job(job),
                    timeout=JOB_TIMEOUT_SECONDS
                )
                
                # Completar
                await handle_job_completion(job, result, session)
                
            except asyncio.TimeoutError:
                logger.error(f"⏱️ Timeout en job {job.id}")
                await handle_job_completion(job, {
                    "success": False,
                    "error": "job_timeout",
                    "retryable": True
                }, session)
                
            except Exception as e:
                logger.exception(f"💥 Error inesperado en job {job.id}: {e}")
                await handle_job_completion(job, {
                    "success": False,
                    "error": str(e),
                    "retryable": True
                }, session)
        
        return True


async def worker_loop():
    """Loop principal del worker"""
    logger.info(f"🚀 VoiceNote Worker iniciado: {WORKER_ID}")
    logger.info(f"   Max concurrent jobs: {MAX_CONCURRENT_JOBS}")
    logger.info(f"   Poll interval: {POLL_INTERVAL_SECONDS}s")
    logger.info(f"   Job timeout: {JOB_TIMEOUT_SECONDS}s")
    logger.info(f"   Transcription: {'✅' if TRANSCRIPTION_AVAILABLE else '❌'}")
    logger.info(f"   AI: {'✅' if AI_AVAILABLE else '❌'}")
    
    while not _shutdown_event.is_set():
        try:
            processed = await process_single_job()
            
            if not processed:
                # No jobs, esperar
                await asyncio.wait_for(
                    _shutdown_event.wait(),
                    timeout=POLL_INTERVAL_SECONDS
                )
                
        except asyncio.TimeoutError:
            pass  # Normal, continue polling
        except Exception as e:
            logger.exception(f"Error en worker loop: {e}")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    
    logger.info("🛑 Worker detenido gracefully")


def signal_handler(sig, frame):
    """Maneja señales de shutdown"""
    logger.info(f"📡 Señal recibida: {sig}, iniciando shutdown...")
    _shutdown_event.set()


async def main():
    """Entry point del worker"""
    # Registrar handlers de señales
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await worker_loop()
    except Exception as e:
        logger.exception(f"Error fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
