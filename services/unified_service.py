"""
Unified Service - Servicio Unificado de Chat
Combina múltiples servicios de chat en una interfaz unificada
"""

import asyncio
from typing import Dict, Any, Optional, AsyncGenerator, List
from datetime import datetime

import logging

logger = logging.getLogger(__name__)


class UnifiedService:
    """
    Servicio unificado que combina chat, búsqueda, documentos y voz
    """
    
    def __init__(self):
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        self.message_history: Dict[str, List[Dict[str, Any]]] = {}
        logger.info("UnifiedService initialized")
    
    async def get_unified_chat_response(
        self, 
        message: str, 
        user_id: str,
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[str, None]:
        """
        Obtiene respuesta unificada con streaming
        
        Args:
            message: Mensaje del usuario
            user_id: ID del usuario
            context: Contexto adicional
        
        Yields:
            Tokens de la respuesta
        """
        try:
            session_id = self._get_or_create_session(user_id)
            
            # Registrar mensaje
            self._add_message_to_history(user_id, "user", message)
            
            # Simular respuesta streaming
            response = f"Procesando tu solicitud: '{message}'"
            
            # Yield tokens word by word
            words = response.split()
            for word in words:
                yield word + " "
                await asyncio.sleep(0.05)  # Simular latencia
            
            # Registrar respuesta
            self._add_message_to_history(user_id, "assistant", response)
            
            logger.info(f"✅ Unified chat response for user {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Error in unified chat: {e}")
            yield f"Error: {str(e)}"
    
    async def process_unified_request(
        self, 
        request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Procesa una solicitud unificada
        
        Args:
            request: Solicitud con tipo y parámetros
        
        Returns:
            Respuesta procesada
        """
        try:
            request_type = request.get("type", "chat")
            user_id = request.get("user_id")
            
            if request_type == "chat":
                return await self._process_chat(request)
            elif request_type == "search":
                return await self._process_search(request)
            elif request_type == "document":
                return await self._process_document(request)
            elif request_type == "voice":
                return await self._process_voice(request)
            else:
                return {
                    "error": f"Unknown request type: {request_type}",
                    "status": "error"
                }
                
        except Exception as e:
            logger.error(f"❌ Error processing unified request: {e}")
            return {
                "error": str(e),
                "status": "error"
            }
    
    async def _process_chat(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Procesa solicitud de chat"""
        message = request.get("message", "")
        user_id = request.get("user_id")
        
        response_text = ""
        async for token in self.get_unified_chat_response(message, user_id):
            response_text += token
        
        return {
            "type": "chat",
            "response": response_text.strip(),
            "status": "success"
        }
    
    async def _process_search(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Procesa solicitud de búsqueda"""
        query = request.get("query", "")
        
        return {
            "type": "search",
            "query": query,
            "results": [
                {
                    "title": f"Result for: {query}",
                    "url": "https://example.com",
                    "snippet": "This is a sample result"
                }
            ],
            "status": "success"
        }
    
    async def _process_document(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Procesa solicitud de documento"""
        doc_type = request.get("doc_type", "pdf")
        content = request.get("content", "")
        
        return {
            "type": "document",
            "doc_type": doc_type,
            "document_id": f"doc_{datetime.utcnow().timestamp()}",
            "status": "generated"
        }
    
    async def _process_voice(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Procesa solicitud de voz"""
        action = request.get("action", "transcribe")
        
        return {
            "type": "voice",
            "action": action,
            "result": "Voice processing completed",
            "status": "success"
        }
    
    def _get_or_create_session(self, user_id: str) -> str:
        """Obtiene o crea una sesión para el usuario"""
        session_id = f"session_{user_id}"
        
        if session_id not in self.active_sessions:
            self.active_sessions[session_id] = {
                "session_id": session_id,
                "user_id": user_id,
                "created_at": datetime.utcnow().isoformat(),
                "last_activity": datetime.utcnow().isoformat(),
                "message_count": 0
            }
            self.message_history[user_id] = []
        
        # Actualizar última actividad
        self.active_sessions[session_id]["last_activity"] = datetime.utcnow().isoformat()
        
        return session_id
    
    def _add_message_to_history(
        self, 
        user_id: str, 
        role: str, 
        content: str
    ) -> None:
        """Agrega un mensaje al historial"""
        if user_id not in self.message_history:
            self.message_history[user_id] = []
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.message_history[user_id].append(message)
        
        # Mantener solo los últimos 50 mensajes
        if len(self.message_history[user_id]) > 50:
            self.message_history[user_id] = self.message_history[user_id][-50:]
    
    async def get_conversation_history(
        self, 
        user_id: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Obtiene el historial de conversación
        
        Args:
            user_id: ID del usuario
            limit: Número máximo de mensajes
        
        Returns:
            Lista de mensajes
        """
        try:
            history = self.message_history.get(user_id, [])
            return history[-limit:]
        except Exception as e:
            logger.error(f"❌ Error getting conversation history: {e}")
            return []
    
    async def clear_conversation(self, user_id: str) -> Dict[str, Any]:
        """
        Limpia la conversación de un usuario
        
        Args:
            user_id: ID del usuario
        
        Returns:
            Estado de la operación
        """
        try:
            if user_id in self.message_history:
                message_count = len(self.message_history[user_id])
                self.message_history[user_id] = []
                
                logger.info(f"✅ Cleared {message_count} messages for user {user_id}")
                
                return {
                    "status": "success",
                    "messages_cleared": message_count
                }
            
            return {
                "status": "success",
                "messages_cleared": 0
            }
            
        except Exception as e:
            logger.error(f"❌ Error clearing conversation: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def get_session_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene información de la sesión
        
        Args:
            user_id: ID del usuario
        
        Returns:
            Información de la sesión
        """
        try:
            session_id = f"session_{user_id}"
            
            if session_id in self.active_sessions:
                session = self.active_sessions[session_id]
                message_count = len(self.message_history.get(user_id, []))
                
                return {
                    **session,
                    "message_count": message_count
                }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting session info: {e}")
            return None
    
    async def get_service_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas del servicio
        
        Returns:
            Estadísticas globales
        """
        try:
            total_sessions = len(self.active_sessions)
            total_messages = sum(
                len(history) for history in self.message_history.values()
            )
            
            return {
                "total_sessions": total_sessions,
                "total_messages": total_messages,
                "active_users": len(self.message_history),
                "status": "operational"
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting service stats: {e}")
            return {}


# Singleton instance
unified_service = UnifiedService()


# Funciones de conveniencia
async def get_unified_response(
    message: str,
    user_id: str,
    context: Dict[str, Any] = None
) -> AsyncGenerator[str, None]:
    """Obtiene respuesta unificada con streaming"""
    async for token in unified_service.get_unified_chat_response(message, user_id, context):
        yield token


async def process_unified_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Procesa una solicitud unificada"""
    return await unified_service.process_unified_request(request)


async def get_conversation_history(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Obtiene historial de conversación"""
    return await unified_service.get_conversation_history(user_id, limit)
