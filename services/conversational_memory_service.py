"""
Conversational Memory Service - Gestiona historial de mensajes del chat actual
Soluciona el problema de que la IA no recuerda el contexto de la conversación en curso.
"""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from services.redis_service import get_cache, set_cache

logger = logging.getLogger("conversational_memory")

_MAX_MESSAGES = int(os.getenv("CONVERSATION_HISTORY_MAX", "20"))
_TTL_SECONDS = int(os.getenv("CONVERSATION_HISTORY_TTL_S", str(30 * 60)))  # 30 min


def _conversation_key(user_id: str) -> str:
    return f"chat:conversation:{user_id}"


def _topic_hash_key(user_id: str) -> str:
    return f"chat:topic:{user_id}"


async def add_message(user_id: str, role: str, content: str, topic: Optional[str] = None) -> None:
    """
    Agrega un mensaje al historial de conversación.
    Si cambia el tema, limpia el historial anterior.
    """
    try:
        key = _conversation_key(user_id)
        
        # Registrar cambio de tema sin borrar historial
        if topic:
            topic_key = _topic_hash_key(user_id)
            current_topic = await get_cache(topic_key)
            if current_topic and current_topic != topic:
                logger.info(f"Nuevo tema detectado para user {user_id}: {topic}")
            await set_cache(topic_key, topic, ttl=_TTL_SECONDS)
        
        # Obtener historial actual
        history = await get_cache(key, default=[])
        if not isinstance(history, list):
            history = []
        
        # Agregar nuevo mensaje
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        }
        history.append(message)
        
        # Mantener solo últimos N mensajes
        if len(history) > _MAX_MESSAGES:
            history = history[-_MAX_MESSAGES:]
        
        await set_cache(key, history, ttl=_TTL_SECONDS)
        
    except Exception as e:
        logger.warning(f"Failed to add message to conversation history: {e}")


async def get_conversation_history(user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Obtiene los últimos mensajes de la conversación actual.
    Retorna lista de dicts con 'role' y 'content' para enviar a la IA.
    """
    try:
        key = _conversation_key(user_id)
        history = await get_cache(key, default=[])
        
        if not isinstance(history, list):
            return []
        
        # Retornar últimos 'limit' mensajes, solo con role y content (sin timestamp)
        messages = history[-limit:] if len(history) > limit else history
        return [{"role": msg.get("role"), "content": msg.get("content")} for msg in messages if isinstance(msg, dict)]
        
    except Exception as e:
        logger.warning(f"Failed to get conversation history: {e}")
        return []


async def clear_conversation(user_id: str) -> None:
    """Limpia el historial de conversación para un usuario."""
    try:
        key = _conversation_key(user_id)
        from services.redis_service import delete_cache
        await delete_cache(key)
        logger.info(f"Cleared conversation history for user {user_id}")
    except Exception as e:
        logger.warning(f"Failed to clear conversation: {e}")


async def detect_topic_change(user_message: str, previous_context: str) -> Optional[str]:
    """
    Detecta si el usuario cambió de tema.
    Retorna el nuevo tema si hay cambio, None si continúa el mismo.
    """
    # Heurística simple: si el mensaje menciona palabras de cambio de tema
    topic_change_markers = [
        "cambiemos de tema", "habla de otra cosa", "olvida eso",
        "nuevo tema", "hablar de", "cuéntame sobre", "qué sabes de",
        "explica", "dime sobre", "a propósito",
    ]
    
    msg_lower = user_message.lower()
    
    for marker in topic_change_markers:
        if marker in msg_lower:
            # Extraer posible nuevo tema
            return msg_lower[:50]
    
    return None
