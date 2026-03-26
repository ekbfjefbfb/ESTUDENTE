"""
Master Chat Tasks v4.0 - New v4.0 task handlers (10 capabilities)
Separado de master_chat_service.py para reducir responsabilidades
"""
import logging
from typing import Dict, Any, Optional, List

from services.groq_ai_service import chat_with_ai, sanitize_ai_text
from services.master_chat_utils import (
    extract_search_query, extract_email_data, extract_service_type,
    extract_translation_text, extract_code_request, extract_text_from_file
)

logger = logging.getLogger("master_chat_tasks_v4")


class V4TaskHandlers:
    """Handlers para las 10 nuevas capacidades v4.0"""
    
    def __init__(self, computer_vision, search_service, email_service, 
                 integrations_service, vision_service):
        self.computer_vision = computer_vision
        self.search = search_service
        self.email = email_service
        self.integrations = integrations_service
        self.vision = vision_service
    
    async def task_detect_objects(self, image_file, message: str) -> Optional[Dict]:
        """Tarea: Detectar objetos en imagen con ComputerVision"""
        try:
            if not self.computer_vision:
                logger.warning("ComputerVisionService no disponible - usando fallback")
                return {"error": "Service not available", "fallback": True}
            
            result = await self.computer_vision.detect_objects(image_file)
            logger.info(f"✅ Objetos detectados: {len(result.get('objects', []))}")
            return result
        except Exception as e:
            logger.error(f"❌ Error detectando objetos: {e}")
            return None
    
    async def task_detect_faces(self, image_file, message: str) -> Optional[Dict]:
        """Tarea: Detectar rostros en imagen con ComputerVision"""
        try:
            if not self.computer_vision:
                logger.warning("ComputerVisionService no disponible - usando fallback")
                return {"error": "Service not available", "fallback": True}
            
            result = await self.computer_vision.detect_faces(image_file)
            logger.info(f"✅ Rostros detectados: {result.get('face_count', 0)}")
            return result
        except Exception as e:
            logger.error(f"❌ Error detectando rostros: {e}")
            return None
    
    async def task_search_documents(self, message: str, user_id: str) -> Optional[Dict]:
        """Tarea: Buscar en documentos del usuario"""
        try:
            if not self.search:
                logger.warning("SearchService no disponible - usando fallback")
                return {"error": "Service not available", "fallback": True}
            
            query = extract_search_query(message)
            result = await self.search.search_user_documents(user_id, query)
            logger.info(f"✅ Búsqueda completada: {len(result.get('results', []))} resultados")
            return result
        except Exception as e:
            logger.error(f"❌ Error en búsqueda: {e}")
            return None
    
    async def task_send_email(self, message: str, user_id: str) -> Optional[Dict]:
        """Tarea: Enviar email automáticamente"""
        try:
            if not self.email:
                logger.warning("EmailService no disponible - usando fallback")
                return {"error": "Service not available", "fallback": True}
            
            email_data = extract_email_data(message)
            result = await self.email.send_email(
                to=email_data["to"],
                subject=email_data["subject"],
                body=email_data["body"],
                from_user=user_id
            )
            logger.info(f"✅ Email enviado a {email_data['to']}")
            return result
        except Exception as e:
            logger.error(f"❌ Error enviando email: {e}")
            return None
    
    async def task_sync_external(self, file, message: str, user_id: str) -> Optional[Dict]:
        """Tarea: Sincronizar con servicio externo (Google/Microsoft/GitHub)"""
        try:
            if not self.integrations:
                logger.warning("IntegrationsService no disponible - usando fallback")
                return {"error": "Service not available", "fallback": True}
            
            service = extract_service_type(message)
            result = await self.integrations.upload_file(
                user_id=user_id,
                file=file,
                service=service
            )
            logger.info(f"✅ Archivo sincronizado con {service}")
            return result
        except Exception as e:
            logger.error(f"❌ Error sincronizando: {e}")
            return None
    
    async def task_translate_text(self, message: str, parameters: Dict) -> Optional[Dict]:
        """Tarea: Traducir texto a otro idioma"""
        try:
            target_lang = parameters.get("target_language", "en")
            text_to_translate = extract_translation_text(message)
            
            # Usar IA para traducción
            prompt = f"Traduce el siguiente texto a {target_lang}:\n\n{text_to_translate}\n\nResponde SOLO con la traducción, sin explicaciones."
            translation = await chat_with_ai(
                messages=[{"role": "user", "content": prompt}],
                fast_reasoning=True
            )
            translation = sanitize_ai_text(translation)
            
            result = {
                "original": text_to_translate,
                "translated": translation,
                "target_language": target_lang
            }
            
            logger.info(f"✅ Texto traducido a {target_lang}")
            return result
        except Exception as e:
            logger.error(f"❌ Error traduciendo: {e}")
            return None
    
    async def task_summarize_text(self, message: str, files: Optional[List]) -> Optional[Dict]:
        """Tarea: Resumir texto o documento"""
        try:
            # Si hay archivo, leer contenido
            if files:
                text_to_summarize = await extract_text_from_file(files[0], self.vision)
            else:
                text_to_summarize = message
            
            # Usar IA para resumir
            prompt = f"Resume el siguiente texto en 5 puntos clave:\n\n{text_to_summarize}\n\nResponde SOLO con el resumen en formato de lista."
            summary = await chat_with_ai(
                messages=[{"role": "user", "content": prompt}],
                fast_reasoning=True
            )
            summary = sanitize_ai_text(summary)
            
            result = {
                "original_length": len(text_to_summarize),
                "summary": summary,
                "compression_ratio": len(summary) / max(len(text_to_summarize), 1)
            }
            
            logger.info(f"✅ Texto resumido: {result['compression_ratio']:.1%} del original")
            return result
        except Exception as e:
            logger.error(f"❌ Error resumiendo: {e}")
            return None
    
    async def task_generate_code(self, message: str, parameters: Dict) -> Optional[Dict]:
        """Tarea: Generar código en lenguaje especificado"""
        try:
            language = parameters.get("language", "python")
            code_request = extract_code_request(message)
            
            # Usar IA para generar código
            prompt = f"Genera código en {language} para: {code_request}\n\nResponde SOLO con el código, sin explicaciones."
            code = await chat_with_ai(
                messages=[{"role": "user", "content": prompt}],
                fast_reasoning=True
            )
            code = sanitize_ai_text(code)
            
            result = {
                "language": language,
                "request": code_request,
                "code": code
            }
            
            logger.info(f"✅ Código generado en {language}")
            return result
        except Exception as e:
            logger.error(f"❌ Error generando código: {e}")
            return None
    
    async def task_extract_data(self, file, message: str) -> Optional[Dict]:
        """Tarea: Extraer datos de imagen/documento (OCR mejorado)"""
        try:
            # Usar VisionPipeline para OCR mejorado
            result = await self.vision.extract_structured_data(file)
            
            logger.info(f"✅ Datos extraídos: {len(result.get('fields', []))} campos")
            return result
        except Exception as e:
            logger.error(f"❌ Error extrayendo datos: {e}")
            return None
    
    async def task_compare_documents(self, file1, file2, message: str) -> Optional[Dict]:
        """Tarea: Comparar dos documentos"""
        try:
            # Extraer texto de ambos documentos
            text1 = await extract_text_from_file(file1, self.vision)
            text2 = await extract_text_from_file(file2, self.vision)
            
            # Usar IA para comparar
            prompt = f"""Compara estos dos documentos y lista las diferencias principales:

DOCUMENTO 1:
{text1[:2000]}

DOCUMENTO 2:
{text2[:2000]}

Responde con una lista de diferencias clave."""
            
            comparison = await chat_with_ai(
                messages=[{"role": "user", "content": prompt}],
                fast_reasoning=True
            )
            comparison = sanitize_ai_text(comparison)
            
            result = {
                "doc1_length": len(text1),
                "doc2_length": len(text2),
                "differences": comparison
            }
            
            logger.info("✅ Documentos comparados")
            return result
        except Exception as e:
            logger.error(f"❌ Error comparando documentos: {e}")
            return None
