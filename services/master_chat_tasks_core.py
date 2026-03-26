"""
Master Chat Tasks Core - Core task handlers (7 capabilities)
Separado de master_chat_service.py para reducir responsabilidades
"""
import logging
from typing import Dict, Any, Optional

from services.groq_ai_service import chat_with_ai, sanitize_ai_text
from services.master_chat_utils import (
    extract_image_prompt, extract_document_topic, extract_text_for_speech,
    determine_edit_type
)

logger = logging.getLogger("master_chat_tasks_core")


class CoreTaskHandlers:
    """Handlers para las 7 capacidades core originales"""
    
    def __init__(self, stability_service, image_editor, document_service, 
                 internet_reports, voice_engine, vision_service):
        self.stability = stability_service
        self.image_editor = image_editor
        self.document = document_service
        self.internet_reports = internet_reports
        self.voice_engine = voice_engine
        self.vision = vision_service
    
    async def task_generate_image(self, message: str, parameters: Dict) -> Optional[Dict]:
        """Tarea: Generar imagen"""
        try:
            prompt = extract_image_prompt(message)
            config = {
                "prompt": prompt,
                "width": parameters.get("width", 1024),
                "height": parameters.get("height", 1024)
            }
            result = await self.stability.generate_image(**config)
            logger.info(f"✅ Imagen generada automáticamente: {prompt}")
            return result
        except Exception as e:
            logger.error(f"❌ Error generando imagen: {e}")
            return None
    
    async def task_edit_image(self, image_file, message: str, parameters: Dict) -> Optional[Dict]:
        """Tarea: Editar imagen"""
        try:
            edit_type = determine_edit_type(message)
            config = {
                "image": image_file,
                "operation": edit_type,
                "prompt": message if edit_type == "ai_edit" else None
            }
            result = await self.image_editor.edit_image(**config)
            logger.info(f"✅ Imagen editada automáticamente: {edit_type}")
            return result
        except Exception as e:
            logger.error(f"❌ Error editando imagen: {e}")
            return None
    
    async def task_create_document(self, message: str, parameters: Dict, user_id: str) -> Optional[Dict]:
        """Tarea: Crear documento"""
        try:
            topic = extract_document_topic(message)
            
            # Si menciona imágenes, usar servicio con imágenes
            if "imagen" in message.lower() or "image" in message.lower():
                config = {
                    "topic": topic,
                    "user_id": user_id,
                    "include_images": True,
                    "format": parameters.get("format", "pdf")
                }
                result = await self.internet_reports.create_report_with_images(**config)
                logger.info(f"✅ Documento con imágenes creado automáticamente: {topic}")
            else:
                config = {
                    "topic": topic,
                    "user_id": user_id,
                    "format": parameters.get("format", "pdf")
                }
                result = await self.document.create_document(**config)
                logger.info(f"✅ Documento creado automáticamente: {topic}")
            
            return result
        except Exception as e:
            logger.error(f"❌ Error creando documento: {e}")
            return None
    
    async def task_analyze_image(self, image_file, message: str) -> Optional[Dict]:
        """Tarea: Analizar imagen"""
        try:
            config = {
                "image": image_file,
                "detailed": "detallado" in message.lower()
            }
            result = await self.vision.analyze_image(**config)
            logger.info("✅ Imagen analizada automáticamente")
            return result
        except Exception as e:
            logger.error(f"❌ Error analizando imagen: {e}")
            return None
    
    async def task_text_to_speech(self, message: str, parameters: Dict) -> Optional[Dict]:
        """Tarea: Convertir a voz con Coqui TTS"""
        try:
            text_to_convert = extract_text_for_speech(message)
            voice = parameters.get("voice", "coqui_enterprise")
            
            # Usar el voice engine empresarial
            audio_data = await self.voice_engine.text_to_speech(text_to_convert, voice_model=voice)
            
            result = {
                "audio_data": audio_data,
                "text": text_to_convert,
                "voice": voice,
                "format": "wav"
            }
            
            logger.info("✅ Audio generado automáticamente")
            return result
        except Exception as e:
            logger.error(f"❌ Error generando audio: {e}")
            return None
    
    async def task_chat_with_ai(self, message: str, user_id: str, intent_analysis: Dict) -> str:
        """Tarea: Chat con IA"""
        try:
            # Enriquecer mensaje con contexto de las acciones que se están ejecutando
            context_message = add_execution_context(message, intent_analysis)
            
            result = await chat_with_ai(
                messages=[{"role": "user", "content": context_message}],
                user=user_id,
                friendly=True
            )
            result = sanitize_ai_text(result)
            logger.info("✅ Respuesta de chat generada")
            return result
        except Exception as e:
            logger.error(f"❌ Error en chat: {e}")
            return "Lo siento, hubo un problema generando la respuesta."


def add_execution_context(message: str, intent_analysis: Dict) -> str:
    """Agrega contexto de lo que se está ejecutando automáticamente"""
    intents = intent_analysis.get("intents", [])
    
    context_parts = [message]
    
    if "generate_image" in intents:
        context_parts.append("(Estoy generando una imagen automáticamente)")
    
    if "create_document" in intents:
        context_parts.append("(Estoy creando un documento automáticamente)")
    
    if "text_to_speech" in intents:
        context_parts.append("(Estoy convirtiendo a audio automáticamente)")
    
    return "\n".join(context_parts)
