"""
Knowledge Extractor Service - IA para Extracción de Contexto
Analiza conversaciones y documentos para extraer conocimiento estructurado

Problema que resuelve:
- Información valiosa perdida en conversaciones largas
- Nadie recuerda qué se decidió o quién debe hacer qué
- Búsqueda manual de información consume horas
- Falta de documentación actualizada

Features:
- extract_from_conversation(): Extrae tasks, decisions, action_items de conversación
- analyze_meeting_transcript(): Convierte transcripción reunión en resumen estructurado
- detect_urgent_items(): Identifica items urgentes que requieren atención
- generate_knowledge_base(): Crea/actualiza KB automáticamente
- find_similar_discussions(): Encuentra discusiones similares históricas
"""

import os
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import json

from services.gpt_service import GPTService

logger = logging.getLogger(__name__)


class KnowledgeExtractorService:
    """
    Service que usa IA (GPT) para extraer conocimiento estructurado
    de conversaciones no estructuradas
    
    Patrones detectados:
    - Tasks: "X, puedes hacer Y", "TODO: Z", "Pendiente implementar W"
    - Decisions: "Decidimos X", "Aprobado Y", "Se descartó Z"
    - Deadlines: "para el viernes", "antes del lunes", "ASAP"
    - Assignments: "Juan se encarga", "@maria esto es para ti"
    - Questions: "¿Cómo podemos...?", "¿Alguien sabe...?"
    - Action Items: "Hay que hacer X", "Necesitamos Y"
    """
    
    def __init__(self):
        self.gpt_service = GPTService()
        logger.info("✅ KnowledgeExtractorService iniciado")
    
    
    async def extract_from_conversation(
        self,
        messages: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Extrae conocimiento estructurado de una conversación
        
        Args:
            messages: List[{
                sender: str,
                text: str,
                timestamp: datetime,
                channel: str
            }]
            context: {
                team_name: str,
                project_name: str,
                participants: List[str]
            }
        
        Returns:
            {
                summary: str,
                key_points: List[str],
                tasks: List[{
                    title: str,
                    assigned_to: str,
                    deadline: Optional[str],
                    priority: str
                }],
                decisions: List[{
                    title: str,
                    decided_by: List[str],
                    rationale: str
                }],
                action_items: List[{
                    item: str,
                    owner: str,
                    urgency: str
                }],
                questions: List[{
                    question: str,
                    asked_by: str,
                    answered: bool
                }],
                confidence: float
            }
        """
        logger.info(f"🔍 Extrayendo conocimiento de {len(messages)} mensajes")
        
        # Construir prompt para GPT
        conversation_text = self._format_conversation_for_ai(messages)
        
        prompt = f"""Analiza la siguiente conversación de equipo y extrae información estructurada.

CONTEXTO:
{json.dumps(context, indent=2) if context else "Sin contexto adicional"}

CONVERSACIÓN:
{conversation_text}

EXTRAE Y FORMATEA EN JSON:
{{
    "summary": "Resumen de 2-3 líneas de qué se discutió",
    "key_points": ["Punto clave 1", "Punto clave 2", "..."],
    "tasks": [
        {{
            "title": "Título tarea",
            "assigned_to": "Nombre persona o 'sin asignar'",
            "deadline": "Fecha mencionada o null",
            "priority": "high|medium|low"
        }}
    ],
    "decisions": [
        {{
            "title": "Decisión tomada",
            "decided_by": ["Nombre 1", "Nombre 2"],
            "rationale": "Por qué se tomó esta decisión"
        }}
    ],
    "action_items": [
        {{
            "item": "Acción específica",
            "owner": "Responsable o 'sin asignar'",
            "urgency": "urgent|normal|low"
        }}
    ],
    "questions": [
        {{
            "question": "Pregunta planteada",
            "asked_by": "Nombre",
            "answered": true/false
        }}
    ]
}}

IMPORTANTE:
- Si no hay items de una categoría, devuelve array vacío []
- Mantén títulos concisos y accionables
- Extrae nombres reales mencionados en la conversación
- Identifica deadlines implícitos ("para mañana" = fecha específica)
"""
        
        try:
            # Llamar a GPT
            response = await self.gpt_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # Más determinístico
                max_tokens=1500
            )
            
            # Parsear JSON response
            extracted = json.loads(response)
            
            # Calcular confidence basado en cantidad de info extraída
            total_items = (
                len(extracted.get('tasks', [])) +
                len(extracted.get('decisions', [])) +
                len(extracted.get('action_items', [])) +
                len(extracted.get('key_points', []))
            )
            confidence = min(0.95, 0.5 + (total_items * 0.05))
            
            extracted['confidence'] = confidence
            
            logger.info(f"✅ Extraído conocimiento con confidence {confidence:.2f}: "
                       f"{len(extracted.get('tasks', []))} tasks, "
                       f"{len(extracted.get('decisions', []))} decisions")
            
            return extracted
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Error parseando respuesta GPT: {e}")
            return self._empty_extraction()
        except Exception as e:
            logger.error(f"❌ Error extrayendo conocimiento: {e}")
            return self._empty_extraction()
    
    
    async def analyze_meeting_transcript(
        self,
        transcript: str,
        meeting_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analiza transcripción de reunión y genera resumen estructurado
        
        Args:
            transcript: Texto transcripción completa
            meeting_metadata: {
                title: str,
                date: datetime,
                participants: List[str],
                duration_minutes: int
            }
        
        Returns:
            {
                executive_summary: str,
                agenda_covered: List[str],
                decisions_made: List[Dict],
                action_items: List[Dict],
                key_discussions: List[Dict],
                next_steps: List[str],
                attendees_contributions: Dict[str, str]
            }
        """
        logger.info(f"📝 Analizando transcripción reunión: {meeting_metadata.get('title')}")
        
        prompt = f"""Analiza esta transcripción de reunión y genera un resumen ejecutivo estructurado.

METADATA:
- Título: {meeting_metadata.get('title')}
- Fecha: {meeting_metadata.get('date')}
- Participantes: {', '.join(meeting_metadata.get('participants', []))}
- Duración: {meeting_metadata.get('duration_minutes')} minutos

TRANSCRIPCIÓN:
{transcript[:4000]}  # Limitar a ~4000 chars

GENERA JSON:
{{
    "executive_summary": "Resumen ejecutivo de 3-4 líneas",
    "agenda_covered": ["Tema 1 discutido", "Tema 2 discutido", "..."],
    "decisions_made": [
        {{
            "decision": "Decisión específica",
            "decided_by": "Nombre o 'equipo'",
            "impact": "high|medium|low"
        }}
    ],
    "action_items": [
        {{
            "action": "Acción específica",
            "owner": "Responsable",
            "deadline": "Fecha o 'TBD'"
        }}
    ],
    "key_discussions": [
        {{
            "topic": "Tema discutido",
            "summary": "Resumen discusión",
            "participants": ["Quiénes participaron activamente"]
        }}
    ],
    "next_steps": ["Paso 1", "Paso 2", "..."],
    "attendees_contributions": {{
        "Nombre 1": "Breve resumen de su participación",
        "Nombre 2": "Breve resumen de su participación"
    }}
}}
"""
        
        try:
            response = await self.gpt_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000
            )
            
            result = json.loads(response)
            
            logger.info(f"✅ Reunión analizada: {len(result.get('decisions_made', []))} decisiones, "
                       f"{len(result.get('action_items', []))} action items")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error analizando transcripción: {e}")
            return {
                'executive_summary': 'Error procesando transcripción',
                'agenda_covered': [],
                'decisions_made': [],
                'action_items': [],
                'key_discussions': [],
                'next_steps': [],
                'attendees_contributions': {}
            }
    
    
    async def detect_urgent_items(
        self,
        messages: List[Dict[str, Any]],
        threshold_hours: int = 24
    ) -> List[Dict[str, Any]]:
        """
        Detecta items urgentes que requieren atención inmediata
        
        Args:
            messages: Mensajes recientes
            threshold_hours: Considerar urgente si deadline < X horas
        
        Returns:
            List[{
                item_type: str (task, question, blocker),
                title: str,
                urgency_score: float (0-1),
                reason: str,
                mentioned_by: str,
                requires_action_from: str,
                deadline: Optional[datetime]
            }]
        """
        logger.info(f"🚨 Detectando items urgentes en {len(messages)} mensajes")
        
        conversation_text = self._format_conversation_for_ai(messages)
        
        prompt = f"""Identifica items URGENTES en esta conversación que requieren atención inmediata.

CONVERSACIÓN:
{conversation_text}

CRITERIOS URGENCIA:
- Deadlines mencionados próximos (<24h)
- Palabras clave: "urgente", "ASAP", "bloqueado", "crítico"
- Preguntas sin responder importantes
- Blockers mencionados
- Clientes esperando respuesta

GENERA JSON:
{{
    "urgent_items": [
        {{
            "item_type": "task|question|blocker|decision",
            "title": "Título conciso",
            "urgency_score": 0.0-1.0,
            "reason": "Por qué es urgente",
            "mentioned_by": "Nombre",
            "requires_action_from": "Nombre o rol",
            "deadline": "Fecha específica o null"
        }}
    ]
}}

DEVUELVE SOLO items verdaderamente urgentes (urgency_score > 0.7)
"""
        
        try:
            response = await self.gpt_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=1000
            )
            
            result = json.loads(response)
            urgent_items = result.get('urgent_items', [])
            
            # Filtrar solo items con urgency_score > 0.7
            urgent_items = [item for item in urgent_items if item.get('urgency_score', 0) > 0.7]
            
            logger.info(f"✅ Detectados {len(urgent_items)} items urgentes")
            return urgent_items
            
        except Exception as e:
            logger.error(f"❌ Error detectando urgentes: {e}")
            return []
    
    
    async def generate_knowledge_base_entry(
        self,
        topic: str,
        related_conversations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Genera entrada de knowledge base basada en conversaciones relacionadas
        
        Args:
            topic: Tema (ej: "Deploy process", "API authentication")
            related_conversations: Conversaciones relacionadas al tema
        
        Returns:
            {
                title: str,
                summary: str,
                detailed_explanation: str,
                steps: List[str],
                common_issues: List[Dict],
                resources: List[str],
                last_updated: datetime,
                contributors: List[str]
            }
        """
        logger.info(f"📚 Generando KB entry para: {topic}")
        
        # Combinar conversaciones relacionadas
        combined_text = "\n\n".join([
            self._format_conversation_for_ai(conv.get('messages', []))
            for conv in related_conversations[:5]  # Limitar a 5 conversaciones
        ])
        
        prompt = f"""Genera una entrada de Knowledge Base sobre el tema "{topic}" basándote en estas conversaciones reales del equipo.

CONVERSACIONES:
{combined_text[:3000]}

GENERA JSON:
{{
    "title": "Título claro y descriptivo",
    "summary": "Resumen de 2-3 líneas",
    "detailed_explanation": "Explicación detallada del tema",
    "steps": ["Paso 1", "Paso 2", "..."],
    "common_issues": [
        {{
            "issue": "Problema común",
            "solution": "Cómo resolverlo"
        }}
    ],
    "resources": ["Link 1", "Link 2", "..."],
    "tips": ["Tip 1", "Tip 2", "..."]
}}

IMPORTANTE:
- Usa información REAL de las conversaciones
- Sé específico y práctico
- Incluye comandos, URLs, nombres reales mencionados
"""
        
        try:
            response = await self.gpt_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=1500
            )
            
            result = json.loads(response)
            result['last_updated'] = datetime.now()
            result['contributors'] = list(set([
                msg.get('sender')
                for conv in related_conversations
                for msg in conv.get('messages', [])
                if msg.get('sender')
            ]))[:10]  # Top 10 contributors
            
            logger.info(f"✅ KB entry generada: {result.get('title')}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error generando KB entry: {e}")
            return {
                'title': topic,
                'summary': 'Error generando contenido',
                'detailed_explanation': '',
                'steps': [],
                'common_issues': [],
                'resources': [],
                'last_updated': datetime.now(),
                'contributors': []
            }
    
    
    async def find_similar_discussions(
        self,
        query: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Encuentra discusiones similares históricas usando embeddings
        
        Args:
            query: Texto query o descripción del tema
            limit: Máximo resultados
        
        Returns:
            List[{
                conversation_id: str,
                title: str,
                similarity_score: float,
                date: datetime,
                participants: List[str],
                summary: str
            }]
        """
        logger.info(f"🔎 Buscando discusiones similares a: {query}")
        
        # TODO: Implementar con embeddings (OpenAI Embeddings API)
        # 1. Generar embedding del query
        # 2. Query vector DB con conversaciones históricas
        # 3. Calcular similaridad cosine
        # 4. Retornar top K resultados
        
        return []
    
    
    # ==========================================
    # HELPER METHODS
    # ==========================================
    
    def _format_conversation_for_ai(self, messages: List[Dict[str, Any]]) -> str:
        """Formatea mensajes para prompt IA"""
        formatted = []
        for msg in messages[:50]:  # Limitar a 50 mensajes
            sender = msg.get('sender', 'Unknown')
            text = msg.get('text', '')
            timestamp = msg.get('timestamp', '')
            
            formatted.append(f"[{timestamp}] {sender}: {text}")
        
        return "\n".join(formatted)
    
    
    def _empty_extraction(self) -> Dict[str, Any]:
        """Retorna estructura vacía si falla extracción"""
        return {
            'summary': 'No se pudo extraer información',
            'key_points': [],
            'tasks': [],
            'decisions': [],
            'action_items': [],
            'questions': [],
            'confidence': 0.0
        }


# Singleton instance
_knowledge_extractor_service = None

def get_knowledge_extractor_service() -> KnowledgeExtractorService:
    """
    Obtiene instancia singleton de KnowledgeExtractorService
    """
    global _knowledge_extractor_service
    if _knowledge_extractor_service is None:
        _knowledge_extractor_service = KnowledgeExtractorService()
    return _knowledge_extractor_service
