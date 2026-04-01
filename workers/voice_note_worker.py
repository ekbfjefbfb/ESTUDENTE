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
from datetime import datetime
from typing import Optional

# Añadir root al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, and_, update, cast, String
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
    from sqlalchemy import text
    
    # Query RAW para evitar problemas de tipo ENUM en PostgreSQL
    five_min_ago = datetime.utcnow() - timedelta(minutes=5)
    
    query = text("""
        SELECT * FROM voice_note_processing_jobs 
        WHERE status::text IN ('pending', 'retrying')
          AND scheduled_at <= NOW()
          AND (locked_at IS NULL OR locked_at < :five_min_ago)
        ORDER BY priority DESC
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    """)
    
    result = await session.execute(query, {"five_min_ago": five_min_ago})
    row = result.fetchone()
    
    if not row:
        return None
    
    # Reconstruir el objeto desde la fila
    job = VoiceNoteProcessingJob(
        id=row.id,
        voice_note_id=row.voice_note_id,
        job_type=row.job_type,
        status=row.status,
        audio_checksum=row.audio_checksum,
        params_hash=row.params_hash,
        job_params=row.job_params,
        result_data=row.result_data,
        error_info=row.error_info,
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        started_at=row.started_at,
        completed_at=row.completed_at,
        duration_ms=row.duration_ms,
        queue_name=row.queue_name,
        priority=row.priority,
        scheduled_at=row.scheduled_at,
        worker_id=row.worker_id,
        locked_at=row.locked_at,
        created_at=row.created_at,
        updated_at=row.updated_at
    )
    
    # Lockear el job
    job.worker_id = WORKER_ID
    job.locked_at = datetime.utcnow()
    job.status = ProcessingJobStatus.RUNNING
    job.attempts += 1
    job.started_at = datetime.utcnow()
    
    await session.commit()
    
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
    """Procesa job de generación de resumen"""
    
    if not AI_AVAILABLE:
        return {
            "success": False,
            "error": "ai_service_unavailable",
            "summary": None
        }
    
    try:
        transcript = voice_note.transcript or ""
        if not transcript.strip():
            return {
                "success": False,
                "error": "no_transcript_available",
                "summary": None
            }
        
        # Prompt para resumen
        prompt = f"""Resume la siguiente transcripción de nota de voz.
        Identifica los puntos clave, acciones pendientes, y organiza la información.
        
        Transcripción:
        {transcript[:8000]}  # Limitar para no exceder contexto
        
        Genera un resumen estructurado en español."""
        
        response = await chat_with_ai(
            message=prompt,
            user_id=voice_note.user_id,
            system_prompt="Eres un asistente especializado en resumir notas de voz."
        )
        
        return {
            "success": True,
            "summary": response.get("response", ""),
            "model": response.get("model", "unknown")
        }
        
    except Exception as e:
        logger.error(f"Error en summarization: {e}")
        return {
            "success": False,
            "error": str(e),
            "summary": None
        }


async def process_extraction_job(
    job: VoiceNoteProcessingJob,
    voice_note: VoiceNote
) -> dict:
    """Procesa job de extracción de items (tareas, etc)"""
    
    if not AI_AVAILABLE:
        return {
            "success": False,
            "error": "ai_service_unavailable",
            "items": [],
            "topics": [],
            "entities": []
        }
    
    try:
        transcript = voice_note.transcript or ""
        if not transcript.strip():
            return {
                "success": False,
                "error": "no_transcript_available",
                "items": [],
                "topics": [],
                "entities": []
            }
        
        # Prompt para extracción
        prompt = f"""Analiza esta transcripción y extrae:
        1. Items de acción (tareas, recordatorios, deadlines)
        2. Temas principales
        3. Entidades nombradas (personas, lugares, organizaciones)
        
        Responde SOLO en JSON con este formato:
        {{
            "items": [{{"type": "task|reminder|deadline", "content": "...", "due_date": "ISO or null"}}],
            "topics": ["tema1", "tema2"],
            "entities": [{{"name": "...", "type": "person|place|org"}}]
        }}
        
        Transcripción:
        {transcript[:8000]}"""
        
        response = await chat_with_ai(
            message=prompt,
            user_id=voice_note.user_id,
            system_prompt="Eres un extractor de información estructurada. Responde solo JSON válido."
        )
        
        # Parsear respuesta
        try:
            result_text = response.get("response", "{}")
            import json
            result = json.loads(result_text)
            
            return {
                "success": True,
                "items": result.get("items", []),
                "topics": result.get("topics", []),
                "entities": result.get("entities", []),
            }
        except json.JSONDecodeError:
            return {
                "success": False,
                "error": "invalid_json_response",
                "items": [],
                "topics": [],
                "entities": []
            }
        
    except Exception as e:
        logger.error(f"Error en extracción: {e}")
        return {
            "success": False,
            "error": str(e),
            "items": [],
            "topics": [],
            "entities": []
        }


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
    
    async with get_primary_session() as session:
        # Cargar voice_note con chunks
        voice_note = await session.execute(
            select(VoiceNote)
            .options(selectinload(VoiceNote.chunks))
            .where(VoiceNote.id == job.voice_note_id)
        )
        voice_note = voice_note.scalar_one()
        
        job_type = job.job_type
        
        if job_type == ProcessingJobType.TRANSCRIPTION:
            result = await process_transcription_job(job, voice_note)
        elif job_type == ProcessingJobType.SUMMARIZATION:
            result = await process_summarization_job(job, voice_note)
        elif job_type == ProcessingJobType.EXTRACTION:
            result = await process_extraction_job(job, voice_note)
        elif job_type == ProcessingJobType.FULL_PIPELINE:
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
        job.status = ProcessingJobStatus.COMPLETED
        job.result_data = result
        job.completed_at = datetime.utcnow()
        
        # Actualizar voice_note con resultados
        voice_note = await session.get(VoiceNote, job.voice_note_id)
        if voice_note:
            # Aplicar resultados según tipo
            if job.job_type == ProcessingJobType.TRANSCRIPTION:
                voice_note.transcript = result.get("transcript", "")
                voice_note.transcript_confidence = result.get("confidence")
                voice_note.status = VoiceNoteStatus.UPLOADED  # Listo para más procesamiento
                
            elif job.job_type == ProcessingJobType.SUMMARIZATION:
                voice_note.summary = result.get("summary")
                voice_note.summary_model = result.get("model")
                
            elif job.job_type == ProcessingJobType.EXTRACTION:
                voice_note.extracted_items = result.get("items", [])
                voice_note.topics = result.get("topics", [])
                voice_note.entities = result.get("entities", [])
                
            elif job.job_type == ProcessingJobType.FULL_PIPELINE:
                voice_note.transcript = result.get("transcript", "")
                voice_note.transcript_confidence = result.get("transcript_confidence")
                voice_note.summary = result.get("summary")
                voice_note.summary_model = result.get("summary_model")
                voice_note.extracted_items = result.get("extracted_items", [])
                voice_note.topics = result.get("topics", [])
                voice_note.entities = result.get("entities", [])
                voice_note.status = VoiceNoteStatus.COMPLETED
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
            job.status = ProcessingJobStatus.RETRYING
            # Schedule retry con backoff exponencial
            backoff_minutes = 2 ** job.attempts
            from sqlalchemy import func
            job.scheduled_at = func.now() + f"{backoff_minutes} minutes"
            logger.warning(f"⚠️ Job {job.id} reintentará en {backoff_minutes}min (attempt {job.attempts})")
        else:
            job.status = ProcessingJobStatus.FAILED
            # Actualizar voice_note status
            voice_note = await session.get(VoiceNote, job.voice_note_id)
            if voice_note:
                voice_note.status = VoiceNoteStatus.ERROR
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
