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

from models.models import RecordingSession, TranscriptChunk, SessionItem, RecordingSessionType, RecordingSessionStatus, SessionItemType, SessionItemStatus
from database.db_enterprise import get_primary_session
from services.groq_voice_service import transcribe_audio_groq
from services.groq_ai_service import chat_with_ai

logger = logging.getLogger("recording_session")


class RecordingSessionService:
    """
    Servicio unificado para gestión de sesiones de grabación y procesamiento de IA
    """

    def __init__(self):
        logger.info("✅ RecordingSessionService inicializado")

    async def start_session(
        self,
        user_id: str,
        title: str,
        teacher_name: Optional[str] = None,
        session_type: str = RecordingSessionType.MANUAL,
        scheduled_id: Optional[str] = None,
        language: str = "es"
    ) -> RecordingSession:
        """
        Inicia una nueva sesión de grabación unificada
        """
        session = RecordingSession(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=title,
            teacher_name=teacher_name,
            session_type=session_type,
            scheduled_id=scheduled_id,
            status=RecordingSessionStatus.RECORDING,
            transcript="",
            language=language,
            started_at=datetime.utcnow()
        )

        async with get_primary_session() as db_session:
            db_session.add(session)
            await db_session.commit()
            await db_session.refresh(session)

        logger.info(f"🎙️ Sesión iniciada: {session.id} ({session_type}) - {title}")
        return session

    async def process_audio_chunk(
        self,
        session_id: str,
        user_id: str,
        audio_bytes: bytes,
        timestamp_seconds: int,
        duration_seconds: Optional[int] = None
    ) -> Optional[str]:
        """
        Procesa un chunk de audio unificado: STT + Chunk + Update Transcript
        """
        try:
            async with get_primary_session() as db_session:
                session = await db_session.get(RecordingSession, session_id)
                if not session or session.user_id != user_id:
                    return None

                # STT con Groq
                text = await transcribe_audio_groq(
                    audio_bytes=audio_bytes,
                    language=session.language
                )

                if not text or not text.strip():
                    return None

                # Guardar chunk unificado
                chunk = TranscriptChunk(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    user_id=user_id,
                    text=text,
                    timestamp_seconds=timestamp_seconds
                )
                db_session.add(chunk)

                # Actualización eficiente del transcript acumulado
                if not hasattr(session, '_transcript_parts'):
                    session._transcript_parts = [session.transcript] if session.transcript else []
                session._transcript_parts.append(text)
                session.transcript = " ".join(session._transcript_parts)
                session.updated_at = datetime.utcnow()

                await db_session.commit()
                return text

        except Exception as e:
            logger.error(f"❌ Error procesando chunk en sesión {session_id}: {e}")
            return None

    async def finalize_session(
        self,
        session_id: str,
        user_id: str
    ) -> Optional[RecordingSession]:
        """
        Finaliza la sesión y genera procesamiento de IA (Resumen + Items)
        """
        async with get_primary_session() as db_session:
            session = await db_session.get(RecordingSession, session_id)

            if not session or session.user_id != user_id:
                logger.error(f"Sesión no encontrada: {session_id}")
                return None

            session.ended_at = datetime.utcnow()
            session.duration_seconds = int(
                (session.ended_at - session.started_at).total_seconds()
            )

            if not session.transcript or not session.transcript.strip():
                session.status = RecordingSessionStatus.ERROR
                await db_session.commit()
                return session

            session.status = RecordingSessionStatus.PROCESSING
            await db_session.commit()

            try:
                # 1. Generar Resumen
                summary = await self._generate_ai_summary(session)
                session.summary = summary
                
                # 2. Extraer Items (Incremental/Final)
                extracted = await self._extract_session_items(session.transcript, session.extracted_state)
                if extracted:
                    session.extracted_state = extracted
                    
                    # Eliminar items previos generados por IA para esta sesión
                    from sqlalchemy import delete
                    await db_session.execute(
                        delete(SessionItem).where(
                            SessionItem.session_id == session_id,
                            SessionItem.source == "ai"
                        )
                    )
                    
                    # Agregar nuevos items
                    order = 0
                    
                    # Key Points
                    for kp in extracted.get("key_points", []):
                        item = SessionItem(
                            id=str(uuid.uuid4()),
                            session_id=session_id,
                            user_id=user_id,
                            item_type=SessionItemType.KEY_POINT,
                            status=SessionItemStatus.SUGGESTED,
                            content=str(kp),
                            order_index=order,
                            source="ai"
                        )
                        db_session.add(item)
                        order += 1
                        
                    # Tasks
                    for t in extracted.get("tasks", []):
                        content = t.get("text") if isinstance(t, dict) else str(t)
                        item = SessionItem(
                            id=str(uuid.uuid4()),
                            session_id=session_id,
                            user_id=user_id,
                            item_type=SessionItemType.TASK,
                            status=SessionItemStatus.SUGGESTED,
                            content=content,
                            due_date=t.get("due_date") if isinstance(t, dict) else None,
                            priority=t.get("priority") if isinstance(t, dict) else None,
                            order_index=order,
                            source="ai"
                        )
                        db_session.add(item)
                        order += 1

                session.status = RecordingSessionStatus.COMPLETED
                await db_session.commit()
                await db_session.refresh(session)

                logger.info(f"✅ Sesión finalizada y procesada: {session_id}")
                return session

            except Exception as e:
                logger.error(f"❌ Error procesando IA en sesión {session_id}: {e}")
                await db_session.rollback()
                session.status = RecordingSessionStatus.ERROR
                await db_session.commit()
                return session

    async def _extract_session_items(self, transcript: str, state: Dict[str, Any]) -> Dict[str, Any]:
        """Extrae items (tareas, puntos clave) usando el extractor existente"""
        try:
            from notes_grpc.extractor import extract_note_segmented
            from notes_grpc.groq_client import GroqClient

            client = GroqClient()
            extracted = await extract_note_segmented(client=client, transcript=transcript, title_hint="")

            return {
                "summary": extracted.summary,
                "lecture_notes": getattr(extracted, "lecture_notes", ""),
                "key_points": extracted.key_points,
                "tasks": [
                    {
                        "text": t.text,
                        "due_date": t.due_date.isoformat() if getattr(t, "due_date", None) else None,
                        "priority": getattr(t, "priority", None),
                    }
                    for t in (extracted.tasks or [])
                ],
            }
        except Exception as e:
            logger.error(f"Error en extracción incremental: {e}")
            return {}

    async def _generate_ai_summary(self, session: RecordingSession) -> str:
        """Llamada unificada a IA para resumen estructurado"""
        max_chars = 25000
        transcript = session.transcript
        if len(transcript) > max_chars:
            transcript = transcript[:max_chars] + "...[truncado]"

        prompt = f"""Genera un resumen académico estructurado de la clase: {session.title}
Profesor: {session.teacher_name or 'N/A'}

TRANSCRIPCIÓN:
{transcript}

INSTRUCCIONES:
1. Resumen ejecutivo (puntos clave)
2. Temas principales y detalles técnicos
3. Tareas, fechas o exámenes mencionados
4. Formato Markdown limpio"""

        messages = [
            {"role": "system", "content": "Eres un asistente académico de élite."},
            {"role": "user", "content": prompt}
        ]

        summary = await chat_with_ai(
            messages=messages,
            user=session.user_id,
            fast_reasoning=True,
            stream=False
        )
        return summary.strip()

    async def list_user_sessions(self, user_id: str, limit: int = 20, offset: int = 0) -> List[RecordingSession]:
        from sqlalchemy import select, desc
        async with get_primary_session() as db_session:
            query = select(RecordingSession).where(RecordingSession.user_id == user_id).order_by(desc(RecordingSession.created_at)).offset(offset).limit(limit)
            result = await db_session.execute(query)
            return list(result.scalars().all())

# Instancia global unificada
recording_session_service = RecordingSessionService()
