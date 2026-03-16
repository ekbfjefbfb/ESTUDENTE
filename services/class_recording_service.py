"""
🎙️ ClassRecordingService - Sistema de grabación de clases eficiente
Streaming STT en tiempo real + Resumen único al final
"""
import asyncio
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import WebSocket

from models.models import ClassRecording, ClassTranscriptChunk
from database.db_enterprise import get_primary_session
from services.groq_voice_service import transcribe_audio_groq
from services.groq_ai_service import chat_with_ai

logger = logging.getLogger("class_recording")


class ClassRecordingService:
    """
    Servicio para grabación de clases con transcripción streaming
    """

    def __init__(self):
        # Sessions activas por recording_id
        self._sessions: Dict[str, Dict[str, Any]] = {}
        logger.info("✅ ClassRecordingService inicializado")

    async def start_recording(
        self,
        user_id: str,
        class_name: str,
        teacher_name: Optional[str] = None,
        language: str = "es"
    ) -> ClassRecording:
        """
        Inicia una nueva grabación de clase

        Args:
            user_id: ID del usuario
            class_name: Nombre de la clase (ej: "Matemáticas 101")
            teacher_name: Nombre del profesor (opcional)
            language: Idioma de la transcripción

        Returns:
            ClassRecording creada
        """
        recording = ClassRecording(
            id=str(uuid.uuid4()),
            user_id=user_id,
            class_name=class_name,
            teacher_name=teacher_name,
            status="recording",
            transcript="",
            transcript_chunks_count=0,
            language=language,
            started_at=datetime.utcnow()
        )

        async with get_primary_session() as session:
            session.add(recording)
            await session.commit()

        logger.info(f"🎙️ Grabación iniciada: {recording.id} - {class_name}")

        return recording

    async def process_audio_chunk(
        self,
        recording_id: str,
        user_id: str,
        audio_bytes: bytes,
        timestamp_seconds: int,
        duration_seconds: Optional[int] = None
    ) -> Optional[str]:
        """
        Procesa un chunk de audio: STT + guarda en DB + actualiza transcript acumulado

        Args:
            recording_id: ID de la grabación
            user_id: ID del usuario (para verificación)
            audio_bytes: Audio en bytes
            timestamp_seconds: Timestamp desde inicio de clase
            duration_seconds: Duración del audio (segundos)

        Returns:
            Texto transcrito o None si falló
        """
        try:
            # STT con Groq
            text = await transcribe_audio_groq(
                audio_bytes=audio_bytes,
                language=None  # Usar auto-detection o pasar desde recording
            )

            if not text or not text.strip():
                return None

            # Guardar chunk individual
            chunk = ClassTranscriptChunk(
                id=str(uuid.uuid4()),
                recording_id=recording_id,
                user_id=user_id,
                text=text,
                timestamp_seconds=timestamp_seconds,
                duration_seconds=duration_seconds
            )

            async with get_primary_session() as session:
                session.add(chunk)

                # Actualizar transcript acumulado en la grabación
                recording = await session.get(ClassRecording, recording_id)
                if recording:
                    recording.transcript += text + " "
                    recording.transcript_chunks_count += 1
                    recording.updated_at = datetime.utcnow()

                await session.commit()

            logger.debug(f"📝 Chunk procesado: {recording_id} - {len(text)} chars")
            return text

        except Exception as e:
            logger.error(f"❌ Error procesando chunk {recording_id}: {e}")
            return None

    async def finalize_recording(
        self,
        recording_id: str,
        user_id: str
    ) -> Optional[ClassRecording]:
        """
        Finaliza la grabación y genera resumen con IA

        Args:
            recording_id: ID de la grabación
            user_id: ID del usuario

        Returns:
            ClassRecording actualizada con resumen o None
        """
        async with get_primary_session() as session:
            recording = await session.get(ClassRecording, recording_id)

            if not recording or recording.user_id != user_id:
                logger.error(f"Grabación no encontrada: {recording_id}")
                return None

            # Calcular duración
            recording.ended_at = datetime.utcnow()
            recording.duration_seconds = int(
                (recording.ended_at - recording.started_at).total_seconds()
            )

            # Verificar si hay transcript para resumir
            if not recording.transcript or not recording.transcript.strip():
                recording.status = "error"
                recording.error_message = "No se transcribió ningún contenido"
                await session.commit()
                return recording

            # Cambiar estado a processing mientras generamos resumen
            recording.status = "processing"
            await session.commit()

        try:
            # Generar resumen con IA (llamada única al final)
            summary = await self._generate_summary(
                class_name=recording.class_name,
                teacher_name=recording.teacher_name,
                transcript=recording.transcript
            )

            # Actualizar con resumen
            async with get_primary_session() as session:
                recording = await session.get(ClassRecording, recording_id)
                recording.summary = summary
                recording.summary_generated_at = datetime.utcnow()
                recording.status = "completed"
                await session.commit()

            logger.info(f"✅ Grabación finalizada: {recording_id} - Resumen generado")
            return recording

        except Exception as e:
            logger.error(f"❌ Error generando resumen {recording_id}: {e}")

            async with get_primary_session() as session:
                recording = await session.get(ClassRecording, recording_id)
                recording.status = "error"
                recording.error_message = f"Error generando resumen: {str(e)}"
                await session.commit()

            return recording

    async def _generate_summary(
        self,
        class_name: str,
        teacher_name: Optional[str],
        transcript: str
    ) -> str:
        """
        Genera resumen de la clase usando IA
        Solo UNA llamada a la IA al final de la clase

        Args:
            class_name: Nombre de la clase
            teacher_name: Nombre del profesor
            transcript: Transcripción completa

        Returns:
            Resumen generado
        """
        # Truncar si es muy largo (límite de contexto)
        max_chars = 20000  # Aprox 5000 tokens
        if len(transcript) > max_chars:
            transcript = transcript[:max_chars] + "\n\n[... Transcripción truncada por longitud ...]"

        prompt = f"""Resume la siguiente clase de {class_name} dictada por {teacher_name or 'el profesor'}.

TRANSCRIPCIÓN COMPLETA:
{transcript}

INSTRUCCIONES:
1. Crea un resumen estructurado y claro
2. Identifica los temas principales y subtemas cubiertos
3. Menciona cualquier tarea, proyecto o deber asignado
4. Usa formato markdown con bullets y secciones claras
5. Mantén un tono académico pero accesible
6. Longitud: aproximadamente 15-20% del texto original
7. Incluye una sección "Puntos Clave" al inicio
8. Si hay fechas importantes o exámenes mencionados, resáltalos

RESUMEN:"""

        messages = [
            {"role": "system", "content": "Eres un asistente académico experto en crear resúmenes estructurados de clases."},
            {"role": "user", "content": prompt}
        ]

        # Llamada a la IA
        summary = await chat_with_ai(
            messages=messages,
            user=None,  # No específico
            fast_reasoning=True,
            stream=False
        )

        return summary.strip()

    async def get_user_recordings(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        status: Optional[str] = None
    ) -> list:
        """
        Lista grabaciones de un usuario

        Args:
            user_id: ID del usuario
            limit: Límite de resultados
            offset: Offset para paginación
            status: Filtrar por status (opcional)

        Returns:
            Lista de ClassRecording
        """
        from sqlalchemy import select, desc

        async with get_primary_session() as session:
            query = select(ClassRecording).where(ClassRecording.user_id == user_id)

            if status:
                query = query.where(ClassRecording.status == status)

            query = query.order_by(desc(ClassRecording.created_at)).offset(offset).limit(limit)

            result = await session.execute(query)
            recordings = result.scalars().all()

            return list(recordings)

    async def get_recording_by_id(
        self,
        recording_id: str,
        user_id: str
    ) -> Optional[ClassRecording]:
        """
        Obtiene una grabación específica

        Args:
            recording_id: ID de la grabación
            user_id: ID del usuario (para verificación de propiedad)

        Returns:
            ClassRecording o None
        """
        async with get_primary_session() as session:
            recording = await session.get(ClassRecording, recording_id)

            if not recording or recording.user_id != user_id:
                return None

            return recording

    async def delete_recording(
        self,
        recording_id: str,
        user_id: str
    ) -> bool:
        """
        Elimina una grabación

        Args:
            recording_id: ID de la grabación
            user_id: ID del usuario

        Returns:
            True si se eliminó, False si no existe o no pertenece al usuario
        """
        async with get_primary_session() as session:
            recording = await session.get(ClassRecording, recording_id)

            if not recording or recording.user_id != user_id:
                return False

            await session.delete(recording)
            await session.commit()

            logger.info(f"🗑️ Grabación eliminada: {recording_id}")
            return True


# Instancia global del servicio
class_recording_service = ClassRecordingService()
