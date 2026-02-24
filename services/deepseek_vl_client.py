"""
Cliente para DeepSeek-VL 33B en Ollama
Modelo multimodal optimizado: Apache 2.0, 60% más barato, 3x más rápido
Perfecto para 50 agentes personales con visión integrada
"""

import httpx
import json
import logging
import base64
from typing import Optional, Dict, Any, List, AsyncGenerator, Union
from pathlib import Path
import asyncio

logger = logging.getLogger(__name__)


class DeepSeekVLClient:
    """
    Cliente HTTP para comunicarse con Ollama ejecutando DeepSeek-VL 33B.
    
    DeepSeek-VL 33B puede:
    - Chat conversacional avanzado (64K contexto)
    - Análisis de imágenes (objetos, personas, texto, escenas)
    - Detección de objetos (reemplaza YOLOv8)
    - OCR (lectura de texto en imágenes)
    - Responder preguntas sobre imágenes
    - Comparación de múltiples imágenes
    - Razonamiento multimodal
    
    Ventajas vs Llama 3.2 90B:
    - 60% más barato ($1,300 vs $2,600/mes)
    - 3x más rápido (40-60 tok/s vs 15-20)
    - Licencia Apache 2.0 (sin restricciones)
    - Calidad 95% similar
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "deepseek-vl:33b",
        timeout: int = 120,  # 2 minutos (modelo más rápido)
        max_retries: int = 3
    ):
        """
        Inicializa el cliente de DeepSeek-VL.
        
        Args:
            base_url: URL del servidor Ollama
            model: Nombre del modelo (deepseek-vl:33b)
            timeout: Timeout en segundos (120s para 33B)
            max_retries: Número de reintentos
        """
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        
        # Cliente HTTP con timeout optimizado
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=30.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
        
        logger.info(f"DeepSeekVLClient inicializado: {base_url} modelo={model}")
    
    async def health_check(self) -> bool:
        """
        Verifica que Ollama esté corriendo y que DeepSeek-VL esté disponible.
        
        Returns:
            True si está saludable, False si no
        """
        try:
            # Check 1: Ollama está corriendo
            response = await self.client.get(f"{self.base_url}/api/tags")
            
            if response.status_code != 200:
                logger.error(f"Ollama no responde: {response.status_code}")
                return False
            
            # Check 2: DeepSeek-VL está instalado
            models_data = response.json()
            available_models = [m.get('name', '') for m in models_data.get('models', [])]
            
            if self.model not in available_models:
                logger.warning(f"Modelo {self.model} no encontrado. Disponibles: {available_models}")
                logger.info("Descarga el modelo con: ollama pull deepseek-vl:33b")
                return False
            
            logger.info(f"✅ DeepSeek-VL disponible: {self.model}")
            return True
            
        except Exception as e:
            logger.error(f"Health check falló: {e}")
            return False
    
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stream: bool = False,
        images: Optional[List[str]] = None
    ) -> Union[Dict[str, Any], AsyncGenerator[str, None]]:
        """
        Chat con Llama Vision (con o sin imágenes).
        
        Args:
            messages: Lista de mensajes en formato OpenAI
                [{"role": "user", "content": "texto"}]
            temperature: Creatividad (0.0 a 1.0)
            max_tokens: Máximo de tokens a generar
            stream: Si es True, retorna generator
            images: Lista de paths a imágenes o URLs o base64
        
        Returns:
            Dict con respuesta o AsyncGenerator si stream=True
        """
        # Preparar el último mensaje con imágenes si hay
        if images and len(images) > 0:
            # Convertir imágenes a base64 si son paths
            image_data = []
            for img in images:
                if img.startswith('http'):
                    # URL - Ollama puede descargarlo
                    image_data.append(img)
                elif img.startswith('data:image'):
                    # Ya es base64
                    image_data.append(img.split(',')[1])
                else:
                    # Path local - convertir a base64
                    try:
                        with open(img, 'rb') as f:
                            b64 = base64.b64encode(f.read()).decode('utf-8')
                            image_data.append(b64)
                    except Exception as e:
                        logger.error(f"Error leyendo imagen {img}: {e}")
            
            # Agregar imágenes al último mensaje
            if messages and image_data:
                last_msg = messages[-1]
                last_msg['images'] = image_data
        
        if stream:
            return self._stream_chat(messages, temperature, max_tokens)
        else:
            return await self._non_stream_chat(messages, temperature, max_tokens)
    
    async def _non_stream_chat(
        self,
        messages: List[Dict[str, Any]],
        temperature: float,
        max_tokens: int
    ) -> Dict[str, Any]:
        """Chat sin streaming (respuesta completa)."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }
        
        for attempt in range(self.max_retries):
            try:
                response = await self.client.post(
                    f"{self.base_url}/api/chat",
                    json=payload
                )
                
                response.raise_for_status()
                data = response.json()
                
                # Extraer respuesta
                assistant_message = data.get('message', {})
                content = assistant_message.get('content', '')
                
                # Métricas
                eval_count = data.get('eval_count', 0)
                eval_duration = data.get('eval_duration', 0)
                
                tokens_per_second = 0
                if eval_duration > 0:
                    tokens_per_second = eval_count / (eval_duration / 1e9)
                
                logger.info(
                    f"Llama Vision respondió: {len(content)} chars, "
                    f"{eval_count} tokens, {tokens_per_second:.1f} tok/s"
                )
                
                return {
                    "content": content,
                    "model": self.model,
                    "tokens": eval_count,
                    "tokens_per_second": tokens_per_second,
                    "finish_reason": "stop"
                }
                
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error (intento {attempt + 1}): {e}")
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
                
            except Exception as e:
                logger.error(f"Error en chat (intento {attempt + 1}): {e}")
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
        
        raise Exception("Max retries alcanzado en _non_stream_chat")
    
    async def _stream_chat(
        self,
        messages: List[Dict[str, Any]],
        temperature: float,
        max_tokens: int
    ) -> AsyncGenerator[str, None]:
        """Chat con streaming (respuesta en chunks)."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }
        
        try:
            async with self.client.stream(
                'POST',
                f"{self.base_url}/api/chat",
                json=payload
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    
                    try:
                        chunk = json.loads(line)
                        message = chunk.get('message', {})
                        content = message.get('content', '')
                        
                        if content:
                            yield content
                        
                        # Último chunk
                        if chunk.get('done', False):
                            logger.info("Streaming completado")
                            break
                            
                    except json.JSONDecodeError:
                        logger.warning(f"Chunk no válido: {line}")
                        continue
                        
        except Exception as e:
            logger.error(f"Error en streaming: {e}")
            raise
    
    async def analyze_image(
        self,
        image_path: str,
        prompt: str = "Describe esta imagen en detalle.",
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """
        Analiza una imagen con Llama Vision.
        
        Args:
            image_path: Path a la imagen o URL
            prompt: Pregunta sobre la imagen
            temperature: Creatividad (0.3 para análisis objetivo)
        
        Returns:
            {
                "description": "...",
                "objects": [...],
                "text": "...",
                "scene": "..."
            }
        """
        messages = [
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        response = await self.chat(
            messages=messages,
            images=[image_path],
            temperature=temperature
        )
        
        return {
            "description": response.get('content', ''),
            "model": self.model,
            "tokens": response.get('tokens', 0)
        }
    
    async def detect_objects(
        self,
        image_path: str,
        temperature: float = 0.2
    ) -> List[Dict[str, Any]]:
        """
        Detecta objetos en una imagen (reemplaza YOLOv8).
        
        Args:
            image_path: Path a la imagen
            temperature: Baja para resultados consistentes
        
        Returns:
            [
                {"object": "persona", "confidence": 0.95, "location": "centro"},
                {"object": "auto", "confidence": 0.88, "location": "izquierda"},
            ]
        """
        prompt = """Analiza esta imagen y lista TODOS los objetos que detectas.
        
Para cada objeto, proporciona:
1. Nombre del objeto
2. Nivel de confianza (0.0 a 1.0)
3. Ubicación aproximada en la imagen

Formato de respuesta en JSON:
[
    {"object": "nombre", "confidence": 0.95, "location": "descripción"},
    ...
]
"""
        
        messages = [{"role": "user", "content": prompt}]
        
        response = await self.chat(
            messages=messages,
            images=[image_path],
            temperature=temperature
        )
        
        content = response.get('content', '')
        
        # Intentar parsear JSON de la respuesta
        try:
            # Buscar JSON en la respuesta
            start = content.find('[')
            end = content.rfind(']') + 1
            
            if start >= 0 and end > start:
                json_str = content[start:end]
                objects = json.loads(json_str)
                return objects
            else:
                logger.warning("No se encontró JSON en respuesta de detección")
                return []
                
        except json.JSONDecodeError as e:
            logger.error(f"Error parseando objetos detectados: {e}")
            # Fallback: retornar descripción como texto
            return [{
                "object": "descripción_general",
                "confidence": 0.8,
                "description": content
            }]
    
    async def extract_text(
        self,
        image_path: str,
        language: str = "es"
    ) -> str:
        """
        Extrae texto de una imagen (OCR con Llama Vision).
        
        Args:
            image_path: Path a la imagen
            language: Idioma esperado
        
        Returns:
            Texto extraído
        """
        prompt = f"""Extrae TODO el texto visible en esta imagen.
        
Idioma esperado: {language}

Reglas:
1. Transcribe exactamente como aparece
2. Mantén el formato (saltos de línea, espacios)
3. Si no hay texto, responde "No se detectó texto"
4. Solo el texto, sin descripciones adicionales
"""
        
        messages = [{"role": "user", "content": prompt}]
        
        response = await self.chat(
            messages=messages,
            images=[image_path],
            temperature=0.1  # Muy baja para transcripción exacta
        )
        
        return response.get('content', '').strip()
    
    async def answer_about_image(
        self,
        image_path: str,
        question: str,
        temperature: float = 0.5
    ) -> str:
        """
        Responde una pregunta específica sobre una imagen.
        
        Args:
            image_path: Path a la imagen
            question: Pregunta del usuario
            temperature: Creatividad
        
        Returns:
            Respuesta a la pregunta
        """
        messages = [
            {
                "role": "user",
                "content": question
            }
        ]
        
        response = await self.chat(
            messages=messages,
            images=[image_path],
            temperature=temperature
        )
        
        return response.get('content', '')
    
    async def generate_completion(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> str:
        """
        Genera una respuesta simple (sin formato de chat).
        
        Args:
            prompt: Texto de entrada
            temperature: Creatividad
            max_tokens: Máximo de tokens
        
        Returns:
            Texto generado
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }
        
        try:
            response = await self.client.post(
                f"{self.base_url}/api/generate",
                json=payload
            )
            
            response.raise_for_status()
            data = response.json()
            
            return data.get('response', '')
            
        except Exception as e:
            logger.error(f"Error en generate_completion: {e}")
            raise
    
    async def list_models(self) -> List[str]:
        """
        Lista todos los modelos disponibles en Ollama.
        
        Returns:
            Lista de nombres de modelos
        """
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            
            data = response.json()
            models = [m.get('name', '') for m in data.get('models', [])]
            
            return models
            
        except Exception as e:
            logger.error(f"Error listando modelos: {e}")
            return []
    
    async def pull_model(self, model_name: str = None) -> bool:
        """
        Descarga un modelo de Ollama.
        
        Args:
            model_name: Nombre del modelo (por defecto usa self.model)
        
        Returns:
            True si descarga exitosa
        """
        target_model = model_name or self.model
        
        logger.info(f"Descargando modelo: {target_model}")
        logger.info("Esto puede tardar 30-60 minutos para Llama 90B...")
        
        payload = {
            "name": target_model,
            "stream": True
        }
        
        try:
            async with self.client.stream(
                'POST',
                f"{self.base_url}/api/pull",
                json=payload,
                timeout=3600  # 1 hora para descargas grandes
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    
                    try:
                        chunk = json.loads(line)
                        status = chunk.get('status', '')
                        
                        # Log progreso
                        if 'completed' in chunk and 'total' in chunk:
                            completed = chunk['completed']
                            total = chunk['total']
                            percent = (completed / total) * 100 if total > 0 else 0
                            logger.info(f"Descarga: {percent:.1f}% - {status}")
                        else:
                            logger.info(status)
                        
                        # Completado
                        if chunk.get('status') == 'success':
                            logger.info(f"✅ Modelo {target_model} descargado exitosamente")
                            return True
                            
                    except json.JSONDecodeError:
                        continue
            
            return True
            
        except Exception as e:
            logger.error(f"Error descargando modelo: {e}")
            return False
    
    async def chat_with_context(
        self,
        question: str,
        context_documents: List[str] = None,
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """
        Chat con contexto de documentos (para modo IA personal en grupos).
        
        Args:
            question: Pregunta del usuario
            context_documents: Lista de IDs de documentos como contexto
            system_prompt: Prompt del sistema
            temperature: Temperatura (0-1)
            max_tokens: Máximo de tokens en respuesta
        
        Returns:
            Respuesta de la IA
        """
        try:
            # Construir contexto
            context_text = ""
            if context_documents and len(context_documents) > 0:
                context_text = f"\n\nContexto disponible: {len(context_documents)} documentos del grupo.\n"
                context_text += f"Documentos: {', '.join(context_documents[:5])}"
            
            # Construir prompt
            final_system_prompt = system_prompt or "Eres un tutor IA personal para estudiantes."
            
            messages = [
                {
                    "role": "system",
                    "content": final_system_prompt + context_text
                },
                {
                    "role": "user",
                    "content": question
                }
            ]
            
            # Llamar al chat normal
            response = await self.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False
            )
            
            return response.get("message", {}).get("content", "")
            
        except Exception as e:
            logger.error(f"Error en chat_with_context: {e}")
            return f"Error al generar respuesta: {str(e)}"
    
    async def close(self):
        """Cierra el cliente HTTP."""
        await self.client.aclose()
        logger.info("DeepSeekVLClient cerrado")


# Instancia global (singleton)
_deepseek_vl_client: Optional[DeepSeekVLClient] = None


async def get_deepseek_vl_client() -> DeepSeekVLClient:
    """
    Obtiene o crea la instancia global de DeepSeekVLClient.
    
    Returns:
        DeepSeekVLClient instance
    """
    global _deepseek_vl_client
    
    if _deepseek_vl_client is None:
        from config import AI_SERVER_URL, AI_MODEL
        
        _deepseek_vl_client = DeepSeekVLClient(
            base_url=AI_SERVER_URL,
            model=AI_MODEL
        )
        
        # Verificar salud
        is_healthy = await _deepseek_vl_client.health_check()
        
        if not is_healthy:
            logger.warning(
                "DeepSeek-VL no está disponible. "
                "Asegúrate de que Ollama esté corriendo y el modelo descargado: ollama pull deepseek-vl:33b"
            )
    
    return _deepseek_vl_client


async def initialize_deepseek_vl_client() -> bool:
    """
    Inicializa el cliente de DeepSeek-VL.
    
    Returns:
        True si inicialización exitosa
    """
    try:
        client = await get_deepseek_vl_client()
        return await client.health_check()
    except Exception as e:
        logger.error(f"Error inicializando DeepSeek-VL: {e}")
        return False
