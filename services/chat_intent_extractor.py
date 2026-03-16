"""
🧠 ChatIntentExtractor - Extrae intenciones de scheduling desde mensajes de chat
"""
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass

from services.groq_ai_service import chat_with_ai
from models.models import ScheduledRecording
from database.db_enterprise import get_primary_session

logger = logging.getLogger("chat_intent_extractor")


@dataclass
class ScheduleIntent:
    """Resultado de extracción de intención de scheduling"""
    has_scheduling_intent: bool
    class_name: Optional[str]
    teacher_name: Optional[str]
    scheduled_datetime: Optional[datetime]
    timezone: str
    duration_minutes: int
    confidence: float
    needs_confirmation: bool
    reasoning: str


class ChatIntentExtractor:
    """
    Extrae intenciones de programar grabaciones desde mensajes de chat.
    Usa IA para detectar fechas, horas, materias, etc.
    """

    def __init__(self):
        logger.info("🧠 ChatIntentExtractor inicializado")

    async def extract_schedule_intent(
        self,
        message: str,
        user_context: Dict[str, Any],
        current_time: Optional[datetime] = None
    ) -> ScheduleIntent:
        """
        Analiza mensaje y extrae SI hay intención de programar grabación.

        Args:
            message: Mensaje del usuario
            user_context: Contexto actual (ubicación, hora, etc.)
            current_time: Hora actual (para "mañana", "próximo martes", etc.)

        Returns:
            ScheduleIntent con los datos extraídos
        """
        if current_time is None:
            current_time = datetime.utcnow()

        # Preparar contexto para el prompt
        context_str = json.dumps(user_context, default=str, ensure_ascii=False)

        prompt = f"""Analiza este mensaje y extrae SI hay intención de programar grabación de una clase.

MENSAJE DEL USUARIO:
"{message}"

CONTEXTO ACTUAL:
- Hora actual: {current_time.isoformat()}
- Zona horaria del usuario: {user_context.get('timezone', 'America/Mexico_City')}
- Ubicación: {user_context.get('location', 'desconocida')}
- Clases recientes: {user_context.get('recent_classes', [])}

INSTRUCCIONES:
1. Detecta si el usuario quiere programar grabación de una clase
2. Extrae fecha/hora (puede ser relativa: "mañana", "el martes", "en 2 horas")
3. Extrae nombre de la clase/materia
4. Extrae nombre del profesor (si se menciona)

Responde SOLO en este formato JSON:
{{
  "has_scheduling_intent": true/false,
  "class_name": "nombre de la materia o null",
  "teacher_name": "nombre del profesor o null",
  "scheduled_datetime_iso": "YYYY-MM-DDTHH:MM:SS o null",
  "timezone": "America/Mexico_City",
  "duration_minutes": 60,
  "confidence": 0.0-1.0,
  "needs_confirmation": true/false,
  "reasoning": "explicación breve de por qué decidiste esto"
}}

REGLAS DE FECHAS:
- "mañana" = fecha actual + 1 día, misma hora si se especifica
- "pasado mañana" = +2 días
- "el martes" = próximo martes
- "a las 2:30" = 14:30 si no especifica AM/PM
- "a las 2:30 PM" = 14:30
- "en 2 horas" = hora actual + 2 horas
- Si no especifica hora, asumir 9:00 AM para clases matutinas, 2:00 PM para vespertinas

REGLAS DE CONFIDENZA:
- confidence > 0.85: intención clara, datos completos
- confidence 0.70-0.85: intención probable pero faltan detalles
- confidence < 0.70: needs_confirmation = true, pedir clarificación al usuario

EJEMPLOS:
"mañana a las 3 tengo clase de Cálculo" → has_scheduling_intent: true, class_name: "Cálculo", scheduled_datetime: mañana 15:00
"recuérdame que el martes tengo Física" → has_scheduling_intent: true, class_name: "Física", scheduled_datetime: próximo martes
"graba mi clase de Álgebra" → has_scheduling_intent: true, pero needs_confirmation: true (falta fecha/hora)
"hola, ¿cómo estás?" → has_scheduling_intent: false"""

        try:
            # Llamar a IA
            response = await chat_with_ai(
                messages=[
                    {"role": "system", "content": "Eres un extractor de intenciones para un sistema de agenda inteligente. Responde SOLO en JSON válido."},
                    {"role": "user", "content": prompt}
                ],
                user=None,
                fast_reasoning=True,
                stream=False,
                json_mode=True
            )

            # Parsear respuesta
            try:
                result = json.loads(response.strip())
            except json.JSONDecodeError:
                logger.error(f"IA no retornó JSON válido: {response[:200]}")
                return ScheduleIntent(
                    has_scheduling_intent=False,
                    class_name=None,
                    teacher_name=None,
                    scheduled_datetime=None,
                    timezone=user_context.get('timezone', 'America/Mexico_City'),
                    duration_minutes=60,
                    confidence=0.0,
                    needs_confirmation=True,
                    reasoning="Error parseando respuesta de IA"
                )

            # Extraer datetime
            scheduled_datetime = None
            if result.get('scheduled_datetime_iso'):
                try:
                    scheduled_datetime = datetime.fromisoformat(result['scheduled_datetime_iso'].replace('Z', '+00:00'))
                except:
                    pass

            return ScheduleIntent(
                has_scheduling_intent=result.get('has_scheduling_intent', False),
                class_name=result.get('class_name'),
                teacher_name=result.get('teacher_name'),
                scheduled_datetime=scheduled_datetime,
                timezone=result.get('timezone', 'America/Mexico_City'),
                duration_minutes=result.get('duration_minutes', 60),
                confidence=result.get('confidence', 0.0),
                needs_confirmation=result.get('needs_confirmation', True),
                reasoning=result.get('reasoning', '')
            )

        except Exception as e:
            logger.error(f"Error extrayendo intención: {e}")
            return ScheduleIntent(
                has_scheduling_intent=False,
                class_name=None,
                teacher_name=None,
                scheduled_datetime=None,
                timezone=user_context.get('timezone', 'America/Mexico_City'),
                duration_minutes=60,
                confidence=0.0,
                needs_confirmation=True,
                reasoning=f"Error: {str(e)}"
            )

    async def create_scheduled_recording(
        self,
        user_id: str,
        intent: ScheduleIntent,
        original_message: str
    ) -> Optional[ScheduledRecording]:
        """
        Crea ScheduledRecording en la base de datos desde un ScheduleIntent.

        Args:
            user_id: ID del usuario
            intent: Intención extraída
            original_message: Mensaje original del usuario

        Returns:
            ScheduledRecording creada o None
        """
        if not intent.has_scheduling_intent or not intent.scheduled_datetime:
            return None

        # Verificar que no sea en el pasado
        if intent.scheduled_datetime < datetime.utcnow() - timedelta(minutes=5):
            logger.warning(f"Intent programado en pasado: {intent.scheduled_datetime}")
            return None

        scheduled = ScheduledRecording(
            id=str(uuid.uuid4()),
            user_id=user_id,
            class_name=intent.class_name or "Clase sin nombre",
            teacher_name=intent.teacher_name,
            scheduled_at=intent.scheduled_datetime,
            timezone=intent.timezone,
            status="pending",
            extracted_from_message=original_message,
            ai_confidence=intent.confidence,
            ai_reasoning=intent.reasoning
        )

        async with get_primary_session() as session:
            session.add(scheduled)
            await session.commit()

        logger.info(f"✅ ScheduledRecording creada: {scheduled.id} - {scheduled.class_name} @ {scheduled.scheduled_at}")
        return scheduled


# Instancia global
chat_intent_extractor = ChatIntentExtractor()
