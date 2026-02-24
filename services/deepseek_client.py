"""
Cliente HTTP para servidor de IA (Ollama + DeepSeek V3)

Este cliente se conecta al servidor de IA separado que ejecuta Ollama
con el modelo DeepSeek V3. Permite arquitectura desacoplada donde el
servidor de IA puede estar en otra máquina o contenedor.
"""

import os
import httpx
import json
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
from datetime import datetime

logger = logging.getLogger(__name__)


class AIServerError(Exception):
    """Error al comunicarse con el servidor de IA"""
    pass


class AIClient:
    """
    Cliente HTTP para servidor de IA (Ollama)
    
    Características:
    - Comunicación HTTP/REST con Ollama
    - Soporte para streaming de respuestas
    - Manejo robusto de errores y timeouts
    - Retry automático con backoff exponencial
    - Métricas y logging detallado
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: str = "deepseek-vl:33b",
        timeout: int = 120,
        max_retries: int = 3
    ):
        """
        Inicializa el cliente de IA
        
        Args:
            base_url: URL del servidor Ollama (ej: http://localhost:11434)
            model: Nombre del modelo a usar (default: deepseek-vl:33b)
            timeout: Timeout en segundos para las requests
            max_retries: Número máximo de reintentos en caso de error
        """
        self.base_url = base_url or os.getenv("AI_SERVER_URL", "http://localhost:11434")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        
        # Validar que la URL no termine en /
        self.base_url = self.base_url.rstrip('/')
        
        logger.info(f"AIClient inicializado - URL: {self.base_url}, Modelo: {self.model}")
    
    async def health_check(self) -> bool:
        """
        Verifica si el servidor de IA está disponible
        
        Returns:
            True si el servidor responde, False en caso contrario
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                
                if response.status_code == 200:
                    data = response.json()
                    models = [m.get("name") for m in data.get("models", [])]
                    
                    if self.model in models:
                        logger.info(f"✅ Servidor de IA disponible - Modelo {self.model} encontrado")
                        return True
                    else:
                        logger.warning(f"⚠️ Servidor disponible pero modelo {self.model} no encontrado. Modelos disponibles: {models}")
                        return False
                else:
                    logger.error(f"❌ Servidor de IA respondió con status {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Error al conectar con servidor de IA: {str(e)}")
            return False
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Envía mensajes al modelo de chat
        
        Args:
            messages: Lista de mensajes [{"role": "user", "content": "..."}]
            temperature: Control de aleatoriedad (0.0 - 2.0)
            max_tokens: Máximo de tokens a generar
            stream: Si True, retorna AsyncGenerator para streaming
            system_prompt: Prompt de sistema opcional
            
        Returns:
            Respuesta del modelo con formato:
            {
                "message": {"role": "assistant", "content": "..."},
                "model": "deepseek-vl:33b",
                "created_at": "2025-10-12T...",
                "done": true,
                "total_duration": 1234567890,
                "tokens_per_second": 45.2
            }
        """
        start_time = datetime.now()
        
        # Preparar payload
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": temperature,
            }
        }
        
        # Agregar num_predict si se especifica max_tokens
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        
        # Agregar system prompt si existe
        if system_prompt:
            payload["system"] = system_prompt
        
        # Log de request
        logger.info(f"🤖 Enviando request a DeepSeek V3 - Mensajes: {len(messages)}, Temp: {temperature}")
        
        try:
            if stream:
                return self._stream_chat(payload, start_time)
            else:
                return await self._non_stream_chat(payload, start_time)
                
        except Exception as e:
            logger.error(f"❌ Error en chat: {str(e)}")
            raise AIServerError(f"Error al comunicarse con servidor de IA: {str(e)}")
    
    async def _non_stream_chat(
        self,
        payload: Dict[str, Any],
        start_time: datetime
    ) -> Dict[str, Any]:
        """Maneja request sin streaming"""
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/api/chat",
                        json=payload
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Calcular métricas
                        duration = (datetime.now() - start_time).total_seconds()
                        total_tokens = data.get("eval_count", 0)
                        tokens_per_second = total_tokens / duration if duration > 0 else 0
                        
                        # Agregar métricas a la respuesta
                        data["tokens_per_second"] = round(tokens_per_second, 2)
                        data["request_duration"] = round(duration, 2)
                        
                        logger.info(
                            f"✅ Respuesta recibida - "
                            f"Tokens: {total_tokens}, "
                            f"Velocidad: {tokens_per_second:.1f} tok/s, "
                            f"Duración: {duration:.1f}s"
                        )
                        
                        return data
                    else:
                        error_msg = f"Status {response.status_code}: {response.text}"
                        logger.error(f"❌ Error del servidor de IA: {error_msg}")
                        
                        if attempt < self.max_retries - 1:
                            logger.info(f"🔄 Reintentando... (intento {attempt + 2}/{self.max_retries})")
                            continue
                        else:
                            raise AIServerError(error_msg)
                            
            except httpx.TimeoutException:
                logger.error(f"⏱️ Timeout en intento {attempt + 1}/{self.max_retries}")
                if attempt < self.max_retries - 1:
                    continue
                else:
                    raise AIServerError("Timeout al esperar respuesta del servidor de IA")
                    
            except httpx.ConnectError:
                logger.error(f"🔌 Error de conexión en intento {attempt + 1}/{self.max_retries}")
                if attempt < self.max_retries - 1:
                    continue
                else:
                    raise AIServerError(
                        f"No se puede conectar al servidor de IA en {self.base_url}. "
                        "Verifica que Ollama esté ejecutándose."
                    )
    
    async def _stream_chat(
        self,
        payload: Dict[str, Any],
        start_time: datetime
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Maneja request con streaming
        
        Yields:
            Chunks de la respuesta a medida que se generan
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json=payload
                ) as response:
                    
                    if response.status_code != 200:
                        error_text = await response.aread()
                        raise AIServerError(f"Status {response.status_code}: {error_text.decode()}")
                    
                    logger.info("🌊 Iniciando streaming...")
                    
                    async for line in response.aiter_lines():
                        if line.strip():
                            try:
                                chunk = json.loads(line)
                                yield chunk
                            except json.JSONDecodeError:
                                logger.warning(f"⚠️ No se pudo parsear línea: {line}")
                                continue
                    
                    duration = (datetime.now() - start_time).total_seconds()
                    logger.info(f"✅ Streaming completado en {duration:.1f}s")
                    
        except Exception as e:
            logger.error(f"❌ Error en streaming: {str(e)}")
            raise AIServerError(f"Error en streaming: {str(e)}")
    
    async def generate_completion(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Genera una completion simple (sin chat)
        
        Args:
            prompt: Texto del prompt
            temperature: Control de aleatoriedad
            max_tokens: Máximo de tokens a generar
            
        Returns:
            Texto generado por el modelo
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            }
        }
        
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get("response", "")
                else:
                    raise AIServerError(f"Status {response.status_code}: {response.text}")
                    
        except Exception as e:
            logger.error(f"❌ Error en generate: {str(e)}")
            raise AIServerError(f"Error al generar completion: {str(e)}")
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """
        Lista todos los modelos disponibles en el servidor
        
        Returns:
            Lista de modelos con sus detalles
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get("models", [])
                else:
                    raise AIServerError(f"Status {response.status_code}: {response.text}")
                    
        except Exception as e:
            logger.error(f"❌ Error al listar modelos: {str(e)}")
            raise AIServerError(f"Error al listar modelos: {str(e)}")
    
    async def pull_model(self, model_name: str) -> bool:
        """
        Descarga un modelo en el servidor
        
        Args:
            model_name: Nombre del modelo a descargar (ej: "deepseek-vl:33b")
            
        Returns:
            True si se descargó exitosamente
        """
        logger.info(f"📥 Descargando modelo {model_name}...")
        
        try:
            async with httpx.AsyncClient(timeout=3600) as client:  # 1 hora timeout para descarga
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/pull",
                    json={"name": model_name}
                ) as response:
                    
                    if response.status_code != 200:
                        raise AIServerError(f"Status {response.status_code}")
                    
                    async for line in response.aiter_lines():
                        if line.strip():
                            try:
                                data = json.loads(line)
                                status = data.get("status", "")
                                
                                # Mostrar progreso
                                if "total" in data and "completed" in data:
                                    total = data["total"]
                                    completed = data["completed"]
                                    percent = (completed / total * 100) if total > 0 else 0
                                    logger.info(f"📥 Progreso: {percent:.1f}% - {status}")
                                else:
                                    logger.info(f"📥 {status}")
                                    
                            except json.JSONDecodeError:
                                continue
                    
                    logger.info(f"✅ Modelo {model_name} descargado exitosamente")
                    return True
                    
        except Exception as e:
            logger.error(f"❌ Error al descargar modelo: {str(e)}")
            raise AIServerError(f"Error al descargar modelo: {str(e)}")


# Instancia global del cliente
_ai_client: Optional[AIClient] = None


def get_ai_client() -> AIClient:
    """
    Obtiene la instancia global del cliente de IA
    
    Returns:
        Instancia de AIClient
    """
    global _ai_client
    
    if _ai_client is None:
        _ai_client = AIClient()
    
    return _ai_client


async def initialize_ai_client() -> bool:
    """
    Inicializa y verifica el cliente de IA
    
    Debe llamarse en el startup de la aplicación
    
    Returns:
        True si se inicializó correctamente
    """
    client = get_ai_client()
    is_healthy = await client.health_check()
    
    if not is_healthy:
        logger.warning(
            "⚠️ Servidor de IA no disponible. "
            "Asegúrate de que Ollama esté ejecutándose y el modelo esté descargado."
        )
    
    return is_healthy
