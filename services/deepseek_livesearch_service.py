"""
Servicio integrado: DeepSeek V3 + LiveSearch

Combina el modelo DeepSeek V3 con búsqueda web en tiempo real
para proporcionar respuestas actualizadas y contextuales.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from services.deepseek_client import get_ai_client, AIClient, AIServerError
from services.livesearch_service import get_livesearch_service, LiveSearchService

logger = logging.getLogger(__name__)


class DeepSeekLiveSearchService:
    """
    Servicio que combina DeepSeek V3 con LiveSearch
    
    Características:
    - Auto-detección de necesidad de búsqueda web
    - Inyección inteligente de contexto de búsqueda
    - Respuestas enriquecidas con información actual
    - Citación de fuentes
    """
    
    def __init__(
        self,
        ai_client: Optional[AIClient] = None,
        search_service: Optional[LiveSearchService] = None
    ):
        """
        Inicializa el servicio integrado
        
        Args:
            ai_client: Cliente de IA (usa global si None)
            search_service: Servicio de búsqueda (usa global si None)
        """
        self.ai_client = ai_client or get_ai_client()
        self.search_service = search_service or get_livesearch_service()
        
        logger.info("DeepSeekLiveSearchService inicializado")
    
    async def chat_with_livesearch(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        force_search: bool = False,
        include_sources: bool = True
    ) -> Dict[str, Any]:
        """
        Procesa mensajes de chat con búsqueda web automática
        
        Args:
            messages: Lista de mensajes del chat
            temperature: Control de aleatoriedad (0.0 - 2.0)
            max_tokens: Máximo de tokens a generar
            force_search: Fuerza búsqueda web aunque no sea detectada
            include_sources: Incluye URLs de fuentes en la respuesta
            
        Returns:
            {
                "message": {"role": "assistant", "content": "..."},
                "model": "deepseek-vl:33b",
                "web_search_used": true,
                "sources": ["https://...", "https://..."],
                "search_query": "término buscado",
                "tokens_per_second": 45.2,
                "total_duration": 2.5
            }
        """
        start_time = datetime.now()
        
        # Obtener último mensaje del usuario
        user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break
        
        if not user_message:
            logger.warning("⚠️ No se encontró mensaje del usuario")
            return await self._chat_without_search(messages, temperature, max_tokens)
        
        # Determinar si se necesita búsqueda web
        needs_search = force_search or self.search_service.should_search(user_message)
        
        if not needs_search:
            logger.info("📝 Respondiendo sin búsqueda web")
            return await self._chat_without_search(messages, temperature, max_tokens)
        
        # Realizar búsqueda web
        logger.info(f"🔍 Búsqueda web activada para: '{user_message[:100]}'")
        
        try:
            # Buscar información
            search_results = await self.search_service.search(user_message)
            
            if not search_results:
                logger.warning("⚠️ Búsqueda no retornó resultados, continuando sin contexto web")
                return await self._chat_without_search(messages, temperature, max_tokens)
            
            # Formatear resultados para el LLM
            search_context = self.search_service.format_results_for_llm(search_results)
            
            # Extraer URLs para citación
            sources = [result["url"] for result in search_results if result.get("url")]
            
            # Crear mensaje del sistema con contexto de búsqueda
            system_prompt = f"""Eres un asistente IA inteligente con acceso a información web actualizada.

{search_context}

IMPORTANTE:
- Usa SOLO la información proporcionada arriba para responder
- Si la información no es suficiente, menciona qué falta
- Cita las fuentes cuando sea relevante usando los números [1], [2], etc.
- Sé preciso con fechas y datos específicos
- Si algo ha cambiado recientemente, menciónalo

Responde de manera natural, conversacional y útil."""
            
            # Agregar instrucción de citación al último mensaje del usuario
            enhanced_messages = messages.copy()
            for i, msg in enumerate(enhanced_messages):
                if msg.get("role") == "user":
                    enhanced_messages[i] = {
                        "role": "user",
                        "content": msg["content"] + "\n\n*Usa la información web proporcionada para dar una respuesta actualizada y cita las fuentes.*"
                    }
            
            # Llamar al modelo con contexto enriquecido
            logger.info("🤖 Enviando request a DeepSeek con contexto de búsqueda")
            
            response = await self.ai_client.chat(
                messages=enhanced_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=system_prompt
            )
            
            # Agregar información de búsqueda a la respuesta
            response["web_search_used"] = True
            response["search_query"] = user_message[:200]
            response["sources"] = sources if include_sources else []
            response["search_results_count"] = len(search_results)
            
            # Agregar fuentes al contenido si se solicita
            if include_sources and sources:
                content = response.get("message", {}).get("content", "")
                sources_text = "\n\n---\n**Fuentes:**\n" + "\n".join(
                    f"[{i+1}] {url}" for i, url in enumerate(sources)
                )
                response["message"]["content"] = content + sources_text
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"✅ Respuesta con LiveSearch completada - "
                f"Fuentes: {len(sources)}, Duración: {duration:.1f}s"
            )
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Error en búsqueda web: {str(e)}, continuando sin contexto")
            return await self._chat_without_search(messages, temperature, max_tokens)
    
    async def _chat_without_search(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int]
    ) -> Dict[str, Any]:
        """
        Procesa chat sin búsqueda web
        
        Args:
            messages: Mensajes del chat
            temperature: Control de aleatoriedad
            max_tokens: Máximo de tokens
            
        Returns:
            Respuesta del modelo
        """
        response = await self.ai_client.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        response["web_search_used"] = False
        response["sources"] = []
        
        return response
    
    async def answer_question(
        self,
        question: str,
        context: Optional[str] = None,
        use_search: bool = True
    ) -> str:
        """
        Responde una pregunta simple con búsqueda automática
        
        Args:
            question: Pregunta del usuario
            context: Contexto adicional opcional
            use_search: Habilitar búsqueda web
            
        Returns:
            Respuesta en texto plano
        """
        messages = []
        
        if context:
            messages.append({
                "role": "system",
                "content": f"Contexto adicional: {context}"
            })
        
        messages.append({
            "role": "user",
            "content": question
        })
        
        response = await self.chat_with_livesearch(
            messages=messages,
            force_search=use_search and self.search_service.should_search(question)
        )
        
        return response.get("message", {}).get("content", "")
    
    async def summarize_with_sources(
        self,
        topic: str,
        num_sources: int = 5
    ) -> Dict[str, Any]:
        """
        Genera un resumen de un tema basado en búsqueda web
        
        Args:
            topic: Tema a resumir
            num_sources: Número de fuentes a consultar
            
        Returns:
            {
                "summary": "Resumen del tema",
                "sources": ["url1", "url2", ...],
                "last_updated": "2025-10-12"
            }
        """
        # Ajustar número de resultados temporalmente
        original_max = self.search_service.max_results
        self.search_service.max_results = num_sources
        
        try:
            # Realizar búsqueda
            search_results = await self.search_service.search(topic)
            
            if not search_results:
                return {
                    "summary": f"No se encontró información reciente sobre '{topic}'",
                    "sources": [],
                    "last_updated": datetime.now().strftime("%Y-%m-%d")
                }
            
            # Crear prompt de resumen
            context = self.search_service.format_results_for_llm(search_results)
            
            messages = [{
                "role": "user",
                "content": f"Resume la siguiente información sobre '{topic}' de manera clara y concisa:\n\n{context}"
            }]
            
            # Generar resumen
            response = await self.ai_client.chat(
                messages=messages,
                temperature=0.5,  # Más determinístico para resúmenes
                system_prompt="Eres un experto en resumir información web. Crea resúmenes claros, precisos y bien estructurados."
            )
            
            sources = [r["url"] for r in search_results if r.get("url")]
            
            return {
                "summary": response.get("message", {}).get("content", ""),
                "sources": sources,
                "last_updated": datetime.now().strftime("%Y-%m-%d"),
                "num_sources_used": len(sources)
            }
            
        finally:
            # Restaurar configuración original
            self.search_service.max_results = original_max


# Instancia global
_deepseek_livesearch: Optional[DeepSeekLiveSearchService] = None


def get_deepseek_livesearch() -> DeepSeekLiveSearchService:
    """
    Obtiene la instancia global del servicio integrado
    
    Returns:
        Instancia de DeepSeekLiveSearchService
    """
    global _deepseek_livesearch
    
    if _deepseek_livesearch is None:
        _deepseek_livesearch = DeepSeekLiveSearchService()
    
    return _deepseek_livesearch


async def chat_with_web(
    messages: List[Dict[str, str]],
    temperature: float = 0.7
) -> Dict[str, Any]:
    """
    Función helper para chat con búsqueda web
    
    Args:
        messages: Mensajes del chat
        temperature: Control de aleatoriedad
        
    Returns:
        Respuesta con búsqueda web si es necesario
    """
    service = get_deepseek_livesearch()
    return await service.chat_with_livesearch(messages, temperature)
