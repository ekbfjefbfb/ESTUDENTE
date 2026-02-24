"""
🌊 Streaming Service - Respuestas IA en Tiempo Real
Stream de respuestas token por token para mejor UX
"""

import logging
import asyncio
from typing import AsyncGenerator, Dict, Any, List, Optional
import json
from datetime import datetime

logger = logging.getLogger("streaming")

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI no disponible")


class StreamingService:
    """
    Servicio de streaming para respuestas IA
    
    Features:
    - Stream token por token
    - Compatible con SSE (Server-Sent Events)
    - Métricas de streaming
    - Fallback a respuestas completas
    """
    
    def __init__(self):
        self.active_streams = 0
        self.total_tokens_streamed = 0
        logger.info("StreamingService inicializado")
    
    async def stream_chat_response(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4",
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> AsyncGenerator[str, None]:
        """
        Stream de respuesta de chat token por token
        
        Args:
            messages: Lista de mensajes del chat
            model: Modelo a usar
            temperature: Temperatura (0-2)
            max_tokens: Máximo de tokens
            
        Yields:
            Tokens individuales de la respuesta
        """
        if not OPENAI_AVAILABLE:
            # Fallback: respuesta mock
            async for chunk in self._mock_stream():
                yield chunk
            return
        
        try:
            self.active_streams += 1
            
            # Crear stream con OpenAI
            stream = await asyncio.to_thread(
                openai.chat.completions.create,
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )
            
            # Iterar sobre chunks
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    self.total_tokens_streamed += 1
                    yield token
                    
                    # Small delay para no saturar
                    await asyncio.sleep(0.01)
            
            self.active_streams -= 1
            logger.info(f"✅ Stream completado")
            
        except Exception as e:
            self.active_streams -= 1
            logger.error(f"Error en streaming: {e}")
            yield f"\n\n[Error: {str(e)}]"
    
    async def stream_with_context(
        self,
        query: str,
        context: str,
        system_prompt: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream de respuesta con contexto (para RAG)
        
        Args:
            query: Pregunta del usuario
            context: Contexto relevante
            system_prompt: Prompt del sistema
        """
        messages = [
            {
                "role": "system",
                "content": system_prompt or "Eres un asistente útil que responde basándose en el contexto proporcionado."
            },
            {
                "role": "user",
                "content": f"Contexto:\n{context}\n\nPregunta: {query}"
            }
        ]
        
        async for token in self.stream_chat_response(messages):
            yield token
    
    async def _mock_stream(self) -> AsyncGenerator[str, None]:
        """Stream mock para testing sin OpenAI"""
        response = "Esta es una respuesta simulada para testing. El streaming permite mostrar el texto progresivamente al usuario."
        
        for word in response.split():
            yield word + " "
            await asyncio.sleep(0.05)
    
    def format_sse(self, data: str) -> str:
        """
        Formatea datos para Server-Sent Events
        
        Args:
            data: Contenido a enviar
            
        Returns:
            String formateado para SSE
        """
        return f"data: {json.dumps({'content': data})}\n\n"
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas de streaming"""
        return {
            "active_streams": self.active_streams,
            "total_tokens_streamed": self.total_tokens_streamed,
            "openai_available": OPENAI_AVAILABLE
        }


# =============================================
# INSTANCIA GLOBAL
# =============================================
streaming_service = StreamingService()
