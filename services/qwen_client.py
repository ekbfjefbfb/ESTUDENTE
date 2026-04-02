from __future__ import annotations

"""Cliente legacy (no usado).

Este proyecto usa Groq para LLM/STT/TTS. Se mantiene el módulo solo por compatibilidad
con imports antiguos; no se inicializa ni realiza llamadas externas.
"""

import logging
import base64
from pathlib import Path
from typing import Optional, List, Dict, Any, AsyncGenerator

logger = logging.getLogger(__name__)


class QwenClient:
    """
    Cliente HTTP legacy (deshabilitado)
    
    Características:
    - Chat texto
    - Análisis de imágenes (visión)
    - Multimodal (texto + imagen)
    - Streaming de respuestas
    """
    
    def __init__(self, *_args, **_kwargs):
        raise RuntimeError("QwenClient is disabled. This project uses Groq.")
    
    async def health_check(self) -> bool:
        """Legacy no-op."""
        try:
            if not self.api_key:
                logger.warning("Legacy API key not configured")
                return False
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            response = await self.client.get(
                f"{self.base_url}/models",
                headers=headers
            )
            response.raise_for_status()
            
            models = response.json().get("data", [])
            model_names = [m.get("id", "") for m in models]
            
            if not any("qwen" in name.lower() for name in model_names):
                logger.warning(f"Qwen model not found. Models available: {model_names[:5]}")
                return False
            
            logger.info("✅ Legacy client available")
            return True
            
        except Exception as e:
            logger.error(f"Health check falló: {e}")
            return False
    
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False
    ) -> str:
        """
        Chat de texto estándar.
        
        Args:
            messages: Lista de mensajes [{"role": "user", "content": "..."}]
            temperature: Creatividad (0.0-2.0)
            max_tokens: Máximo de tokens en respuesta
            stream: Si hacer streaming
        
        Returns:
            Respuesta del modelo
        """
        try:
            logger.info(f"🤖 Chat request - Mensajes: {len(messages)}, Temp: {temperature}")
            
            response = await self.client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "options": {"num_predict": max_tokens},
                    "stream": stream
                }
            )
            response.raise_for_status()
            
            result = response.json()
            return result["message"]["content"]
            
        except Exception as e:
            logger.error(f"Error en chat: {e}")
            raise
    
    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7
    ) -> AsyncGenerator[str, None]:
        """
        Chat con streaming de respuestas token por token.
        
        Args:
            messages: Lista de mensajes
            temperature: Creatividad
        
        Yields:
            Tokens de la respuesta
        """
        try:
            async with self.client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": True
                }
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        import json
                        data = json.loads(line)
                        if "message" in data and "content" in data["message"]:
                            yield data["message"]["content"]
        except Exception as e:
            logger.error(f"Error en streaming: {e}")
            raise
    
    async def analyze_image(
        self,
        image_path: str,
        prompt: str = "Describe esta imagen en detalle",
        temperature: float = 0.7
    ) -> str:
        """
        Analiza una imagen (visión).
        
        Args:
            image_path: Ruta al archivo de imagen
            prompt: Pregunta sobre la imagen
            temperature: Creatividad
        
        Returns:
            Análisis de la imagen
        """
        try:
            logger.info(f"👁️ Análisis de imagen: {Path(image_path).name}")
            
            # Leer imagen y convertir a base64
            with open(image_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode()
            
            messages = [{
                "role": "user",
                "content": prompt,
                "images": [image_b64]
            }]
            
            response = await self.client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": False
                }
            )
            response.raise_for_status()
            
            result = response.json()
            return result["message"]["content"]
            
        except Exception as e:
            logger.error(f"Error en análisis de imagen: {e}")
            raise
    
    async def transcribe_audio(
        self,
        audio_path: str,
        language: str = "es"
    ) -> str:
        """
        Transcribe audio a texto (STT).
        
        Args:
            audio_path: Ruta al archivo de audio
            language: Idioma del audio
        
        Returns:
            Texto transcrito
        """
        try:
            logger.info(f"🎙️ Transcribiendo audio: {Path(audio_path).name}")
            
            # Leer audio y convertir a base64
            with open(audio_path, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode()
            
            messages = [{
                "role": "user",
                "content": f"Transcribe este audio en {language}",
                "audio": [audio_b64]
            }]
            
            response = await self.client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False
                }
            )
            response.raise_for_status()
            
            result = response.json()
            return result["message"]["content"]
            
        except Exception as e:
            logger.error(f"Error en transcripción: {e}")
            # Fallback a Whisper si está disponible
            logger.warning("Fallback a Whisper...")
            raise
    
    async def multimodal_chat(
        self,
        text: str,
        images: Optional[List[str]] = None,
        audio: Optional[str] = None,
        temperature: float = 0.7
    ) -> str:
        """
        Chat multimodal (texto + imágenes + audio combinados).
        
        Args:
            text: Texto del mensaje
            images: Lista de rutas a imágenes
            audio: Ruta a archivo de audio
            temperature: Creatividad
        
        Returns:
            Respuesta del modelo
        """
        try:
            logger.info(f"🌐 Chat multimodal - Texto: ✓, Imágenes: {len(images) if images else 0}, Audio: {'✓' if audio else '✗'}")
            
            message = {
                "role": "user",
                "content": text
            }
            
            # Añadir imágenes
            if images:
                image_b64_list = []
                for img_path in images:
                    with open(img_path, "rb") as f:
                        image_b64_list.append(base64.b64encode(f.read()).decode())
                message["images"] = image_b64_list
            
            # Añadir audio
            if audio:
                with open(audio, "rb") as f:
                    audio_b64 = base64.b64encode(f.read()).decode()
                message["audio"] = [audio_b64]
            
            response = await self.client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [message],
                    "temperature": temperature,
                    "stream": False
                }
            )
            response.raise_for_status()
            
            result = response.json()
            return result["message"]["content"]
            
        except Exception as e:
            logger.error(f"Error en multimodal: {e}")
            raise
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """Legacy."""
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            response = await self.client.get(f"{self.base_url}/models", headers=headers)
            response.raise_for_status()
            return response.json().get("data", [])
        except Exception as e:
            logger.error(f"Error listando modelos: {e}")
            return []
    
    async def close(self):
        """Cierra el cliente HTTP."""
        await self.client.aclose()
        logger.info("QwenClient cerrado")


# Instancia global singleton
_qwen_client: Optional[QwenClient] = None


async def get_qwen_client() -> QwenClient:
    """
    Obtiene o crea la instancia global de QwenClient (legacy).
    """
    global _qwen_client
    
    raise RuntimeError("QwenClient is disabled. This project uses Groq.")


async def initialize_qwen_client() -> bool:
    """
    Inicializa el cliente de Qwen y verifica que funciona.
    
    Returns:
        True si está disponible, False si no
    """
    return False


__all__ = [
    "QwenClient",
    "get_qwen_client",
    "initialize_qwen_client"
]
