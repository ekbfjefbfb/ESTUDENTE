"""
Master Chat Service Enterprise - IA que detecta y ejecuta automáticamente
Optimizado para multiusuario y alta carga
Versión: Production v4.0 - CON 17 CAPACIDADES
"""
import asyncio
import logging
import re
from typing import Dict, List, Optional, Any
from datetime import datetime
from config import AI_MODEL
import json_log_formatter
from utils.safe_metrics import Counter, Histogram

# Importar servicios empresariales optimizados
from services.gpt_service import chat_with_ai
from services.stability_service import StabilityService
from services.image_edit_service import ImageEditService
from services.voice_service import VoiceEngineEnterprise
from services.vision_pipeline_service import VisionPipelineService
from services.document_service import DocumentServiceEnterprise
from services.internet_image_report_service import InternetImageReportService

# 🚀 NUEVOS SERVICIOS INTEGRADOS (v4.0) - Con manejo de errores
try:
    from services.computer_vision_service import ComputerVisionService
    CV_AVAILABLE = True
except ImportError:
    ComputerVisionService = None
    CV_AVAILABLE = False

try:
    from services.search_service import SearchService
    SEARCH_AVAILABLE = True
except ImportError:
    SearchService = None
    SEARCH_AVAILABLE = False

try:
    from services.email_service import EmailService
    EMAIL_AVAILABLE = True
except ImportError:
    EmailService = None
    EMAIL_AVAILABLE = False

try:
    from services.integrations_service import IntegrationsService
    INTEGRATIONS_AVAILABLE = True
except ImportError:
    IntegrationsService = None
    INTEGRATIONS_AVAILABLE = False

DEEPSEEK_SEARCH_AVAILABLE = False

# =============================================
# CONFIGURACIÓN DE LOGGING EMPRESARIAL
# =============================================
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("master_chat_enterprise")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# =============================================
# MÉTRICAS PROMETHEUS
# =============================================
MASTER_CHAT_REQUESTS = Counter(
    "master_chat_requests_total",
    "Total master chat requests",
    ["user_id", "intent_type", "status"]
)

MASTER_CHAT_PROCESSING_TIME = Histogram(
    "master_chat_processing_seconds",
    "Master chat processing time"
)

class MasterChatServiceEnterprise:
    """
    IA Maestra empresarial que decide automáticamente qué servicios usar
    Optimizada para multiusuario y alta carga
    """
    
    def __init__(self):
        # ====================================
        # SERVICIOS EMPRESARIALES ORIGINALES
        # ====================================
        self.stability = StabilityService()
        self.image_editor = ImageEditService()
        
        # Voice service empresarial con Whisper/Coqui
        self.voice_engine = VoiceEngineEnterprise()
        
        self.vision = VisionPipelineService()
        self.document = DocumentServiceEnterprise()
        self.internet_reports = InternetImageReportService()
        
        # ====================================
        # 🚀 NUEVOS SERVICIOS v4.0
        # ====================================
        self.computer_vision = ComputerVisionService() if CV_AVAILABLE else None
        self.search = SearchService() if SEARCH_AVAILABLE else None
        self.email = EmailService() if EMAIL_AVAILABLE else None
        self.integrations = IntegrationsService() if INTEGRATIONS_AVAILABLE else None
        self.deepseek_search = DeepSeekLiveSearchService() if DEEPSEEK_SEARCH_AVAILABLE else None
        
        # Semáforo para limitar concurrencia
        self._concurrency_limit = asyncio.Semaphore(50)  # Max 50 requests concurrentes
        
        # ====================================
        # PATRONES DE DETECCIÓN AUTOMÁTICA v4.0 (17 CAPACIDADES)
        # ====================================
        self.auto_patterns = {
            # ====================================
            # 🎨 CAPACIDADES ORIGINALES (7)
            # ====================================
            "generate_image": [
                r"crea\s+(?:una\s+)?imagen",
                r"genera\s+(?:una\s+)?imagen", 
                r"dibuja\s+(?:una\s+)?imagen",
                r"haz\s+(?:una\s+)?imagen",
                r"create\s+(?:an?\s+)?image",
                r"generate\s+(?:an?\s+)?image"
            ],
            "edit_image": [
                r"edita\s+(?:la\s+)?imagen",
                r"mejora\s+(?:la\s+)?imagen",
                r"modifica\s+(?:la\s+)?imagen",
                r"cambia\s+(?:la\s+)?imagen"
            ],
            "create_document": [
                r"crea\s+(?:un\s+)?(?:pdf|documento)",
                r"genera\s+(?:un\s+)?(?:pdf|documento)",
                r"haz\s+(?:un\s+)?(?:pdf|documento)",
                r"créame\s+(?:un\s+)?(?:pdf|documento)"
            ],
            "text_to_speech": [
                r"convierte\s+(?:a\s+)?(?:voz|audio)",
                r"lee\s+(?:este\s+)?texto",
                r"text\s+to\s+speech",
                r"dilo\s+en\s+voz"
            ],
            "analyze_image": [
                r"analiza\s+(?:la\s+)?imagen",
                r"qué\s+(?:hay\s+)?(?:en\s+)?(?:la\s+)?imagen",
                r"describe\s+(?:la\s+)?imagen",
                r"explica\s+(?:la\s+)?imagen"
            ],
            
            # ====================================
            # 🚀 NUEVAS CAPACIDADES v4.0 (10)
            # ====================================
            
            # 1. Detección de objetos
            "detect_objects": [
                r"detecta\s+(?:objetos|cosas)",
                r"qué\s+objetos\s+hay",
                r"encuentra\s+(?:objetos|cosas)",
                r"detect\s+objects",
                r"identifica\s+objetos"
            ],
            
            # 2. Detección de rostros
            "detect_faces": [
                r"detecta\s+(?:rostros|caras|personas)",
                r"cuántas\s+personas\s+hay",
                r"reconocimiento\s+facial",
                r"detect\s+faces",
                r"identificar\s+rostros"
            ],
            
            # 3. Búsqueda en documentos
            "search_documents": [
                r"busca\s+en\s+(?:mis\s+)?documentos",
                r"encuentra\s+(?:en\s+)?(?:mis\s+)?documentos",
                r"qué\s+dice\s+mi\s+documento\s+sobre",
                r"search\s+in\s+(?:my\s+)?documents",
                r"consulta\s+(?:mis\s+)?documentos"
            ],
            
            # 4. Envío de emails
            "send_email": [
                r"envía\s+(?:un\s+)?(?:email|correo)",
                r"manda\s+(?:un\s+)?(?:email|correo)",
                r"send\s+(?:an?\s+)?email",
                r"escribe\s+(?:un\s+)?email\s+a"
            ],
            
            # 5. Sincronización con servicios externos
            "sync_external": [
                r"sincroniza\s+(?:con\s+)?(?:google|microsoft|github)",
                r"sube\s+a\s+(?:drive|onedrive|github)",
                r"guarda\s+en\s+(?:google|microsoft|drive)",
                r"sync\s+with",
                r"exporta\s+a\s+(?:google|microsoft)"
            ],
            
            # 6. Traducción
            "translate_text": [
                r"traduce\s+(?:a|al)\s+\w+",
                r"translate\s+to\s+\w+",
                r"en\s+\w+\s+(?:por favor|please)",
                r"cómo\s+se\s+dice\s+en\s+\w+",
                r"pásalo\s+a\s+\w+"
            ],
            
            # 7. Resumen de textos
            "summarize_text": [
                r"resume\s+(?:este\s+)?(?:texto|documento)",
                r"haz\s+un\s+resumen",
                r"summarize\s+(?:this\s+)?(?:text|document)",
                r"dame\s+un\s+resumen",
                r"sintetiza\s+(?:este\s+)?(?:texto|documento)"
            ],
            
            # 8. Generación de código
            "generate_code": [
                r"genera\s+código\s+(?:en\s+)?(\w+)?",
                r"escribe\s+(?:un\s+)?script\s+(?:en\s+)?(\w+)?",
                r"create\s+(?:a\s+)?script",
                r"programa\s+(?:en\s+)?(\w+)?",
                r"código\s+para"
            ],
            
            # 9. Extracción de datos
            "extract_data": [
                r"extrae\s+(?:datos|información)",
                r"lee\s+(?:los\s+)?datos\s+de",
                r"extract\s+data\s+from",
                r"obtén\s+(?:los\s+)?datos",
                r"saca\s+la\s+información"
            ],
            
            # 10. Comparación de documentos
            "compare_documents": [
                r"compara\s+(?:estos\s+)?documentos",
                r"diferencias\s+entre",
                r"compare\s+(?:these\s+)?documents",
                r"qué\s+cambió\s+entre",
                r"contrasta\s+(?:estos\s+)?documentos"
            ]
        }
        
        logger.info("🚀 Master Chat Service Enterprise inicializado - Modo MULTIUSUARIO")
    
    async def process_unified_request(
        self,
        message: str,
        user_id: str,
        files: Optional[List] = None,
        auto_generation: bool = True
    ) -> Dict[str, Any]:
        """
        Procesa mensaje multiusuario y EJECUTA AUTOMÁTICAMENTE lo que detecta
        Optimizado para alta carga y concurrencia
        """
        # Control de concurrencia empresarial
        async with self._concurrency_limit:
            start_time = datetime.utcnow()
            
            try:
                # Métricas inicio
                MASTER_CHAT_REQUESTS.labels(
                    user_id=user_id[:8] if user_id else "anon",
                    intent_type="processing",
                    status="started"
                ).inc()
                
                # 1. DETECCIÓN AUTOMÁTICA de intenciones
                intent_analysis = await self._auto_detect_intentions(message, files)
                
                logger.info({
                    "event": "intent_detected",
                    "user_id": user_id,
                    "intents": intent_analysis,
                    "message_length": len(message)
                })
                
                # 2. EJECUCIÓN AUTOMÁTICA en paralelo optimizada
                results = await self._auto_execute_all(
                    intent_analysis, message, user_id, files
                )
                
                # 3. RESPUESTA UNIFICADA inteligente
                unified_response = await self._create_smart_response(
                    intent_analysis, results, message
                )
                
                # 4. Métricas y respuesta final
                processing_time = (datetime.utcnow() - start_time).total_seconds()
                
                MASTER_CHAT_PROCESSING_TIME.observe(processing_time)
                MASTER_CHAT_REQUESTS.labels(
                    user_id=user_id[:8] if user_id else "anon",
                    intent_type="success",
                    status="completed"
                ).inc()
                
                logger.info({
                    "event": "request_completed",
                    "user_id": user_id,
                    "processing_time": processing_time,
                    "intents_executed": len(intent_analysis.get("intents", []))
                })
                
                return {
                    "response": unified_response,
                    "generated_content": self._extract_generated_content(results),
                    "files": self._extract_generated_files(results),
                    "intent": intent_analysis,
                    "summary": self._create_execution_summary(results),
                    "processing_time": processing_time
                }
                
            except Exception as e:
                # Métricas de error
                processing_time = (datetime.utcnow() - start_time).total_seconds()
                MASTER_CHAT_REQUESTS.labels(
                    user_id=user_id[:8] if user_id else "anon",
                    intent_type="error",
                    status="failed"
                ).inc()
                
                logger.error({
                    "event": "request_error",
                    "user_id": user_id,
                    "error": str(e),
                    "processing_time": processing_time
                })
                
                # Fallback a chat normal con IA local
                fallback = await chat_with_ai(
                    messages=[{"role": "user", "content": message}],
                    user=user_id,
                    fast_reasoning=True
                )
                
                return {
                    "response": fallback,
                    "generated_content": {},
                    "files": [],
                    "error": str(e),
                    "fallback": True,
                    "processing_time": processing_time
                }
    
    async def _auto_detect_intentions(
        self, 
        message: str, 
        files: Optional[List]
    ) -> Dict[str, Any]:
        """
        Detección AUTOMÁTICA de todas las intenciones del usuario
        """
        message_lower = message.lower()
        detected_intents = []
        
        # 1. Detección por patrones
        for intent_type, patterns in self.auto_patterns.items():
            for pattern in patterns:
                if re.search(pattern, message_lower):
                    detected_intents.append(intent_type)
                    break
        
        # 2. Detección por archivos subidos
        if files:
            for file in files:
                if file and hasattr(file, 'content_type'):
                    if file.content_type.startswith('image/'):
                        if not any(intent in detected_intents for intent in ['edit_image', 'analyze_image']):
                            # Si sube imagen sin comando específico, analizar
                            detected_intents.append('analyze_image')
        
        # 3. Detección inteligente con IA
        ai_intents = await self._ai_smart_detection(message)
        detected_intents.extend(ai_intents)
        
        # 4. Siempre incluir chat si no hay otras intenciones
        if not detected_intents:
            detected_intents.append('general_chat')
        elif 'general_chat' not in detected_intents:
            detected_intents.append('general_chat')  # Chat + otras acciones
        
        return {
            "intents": list(set(detected_intents)),
            "primary_intent": detected_intents[0] if detected_intents else "general_chat",
            "auto_mode": True,
            "parameters": self._extract_smart_parameters(message),
            "confidence": len(detected_intents) * 0.3
        }
    
    async def _auto_execute_all(
        self,
        intent_analysis: Dict,
        message: str,
        user_id: str,
        files: Optional[List]
    ) -> Dict[str, Any]:
        """
        EJECUTA AUTOMÁTICAMENTE todos los servicios detectados EN PARALELO
        🚀 v4.0 - Con 17 capacidades integradas
        """
        tasks = []
        results = {}
        
        intents = intent_analysis["intents"]
        parameters = intent_analysis["parameters"]
        
        # ====================================
        # CREAR TAREAS ASÍNCRONAS PARALELAS
        # ====================================
        
        # 🎨 CAPACIDADES ORIGINALES
        if "generate_image" in intents:
            tasks.append(self._task_generate_image(message, parameters))
        
        if "edit_image" in intents and files:
            tasks.append(self._task_edit_image(files[0], message, parameters))
        
        if "create_document" in intents:
            tasks.append(self._task_create_document(message, parameters, user_id))
        
        if "analyze_image" in intents and files:
            tasks.append(self._task_analyze_image(files[0], message))
        
        if "text_to_speech" in intents:
            tasks.append(self._task_text_to_speech(message, parameters))
        
        # 🚀 NUEVAS CAPACIDADES v4.0
        if "detect_objects" in intents and files:
            tasks.append(self._task_detect_objects(files[0], message))
        
        if "detect_faces" in intents and files:
            tasks.append(self._task_detect_faces(files[0], message))
        
        if "search_documents" in intents:
            tasks.append(self._task_search_documents(message, user_id))
        
        if "send_email" in intents:
            tasks.append(self._task_send_email(message, user_id))
        
        if "sync_external" in intents and files:
            tasks.append(self._task_sync_external(files[0], message, user_id))
        
        if "translate_text" in intents:
            tasks.append(self._task_translate_text(message, parameters))
        
        if "summarize_text" in intents:
            tasks.append(self._task_summarize_text(message, files))
        
        if "generate_code" in intents:
            tasks.append(self._task_generate_code(message, parameters))
        
        if "extract_data" in intents and files:
            tasks.append(self._task_extract_data(files[0], message))
        
        if "compare_documents" in intents and files and len(files) >= 2:
            tasks.append(self._task_compare_documents(files[0], files[1], message))
        
        # CHAT CON IA (siempre último para contexto completo)
        if "general_chat" in intents:
            tasks.append(self._task_chat_with_ai(message, user_id, intent_analysis))
        
        # ====================================
        # EJECUTAR TODO EN PARALELO
        # ====================================
        if tasks:
            task_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Mapear resultados a nombres
            task_names = []
            if "generate_image" in intents:
                task_names.append("generated_image")
            if "edit_image" in intents and files:
                task_names.append("edited_image")
            if "create_document" in intents:
                task_names.append("document")
            if "analyze_image" in intents and files:
                task_names.append("image_analysis")
            if "text_to_speech" in intents:
                task_names.append("audio")
            # Nuevas capacidades
            if "detect_objects" in intents and files:
                task_names.append("detected_objects")
            if "detect_faces" in intents and files:
                task_names.append("detected_faces")
            if "search_documents" in intents:
                task_names.append("search_results")
            if "send_email" in intents:
                task_names.append("email_sent")
            if "sync_external" in intents and files:
                task_names.append("sync_result")
            if "translate_text" in intents:
                task_names.append("translation")
            if "summarize_text" in intents:
                task_names.append("summary")
            if "generate_code" in intents:
                task_names.append("code")
            if "extract_data" in intents and files:
                task_names.append("extracted_data")
            if "compare_documents" in intents and files and len(files) >= 2:
                task_names.append("comparison")
            if "general_chat" in intents:
                task_names.append("chat_response")
            
            # Procesar resultados
            for i, result in enumerate(task_results):
                if i < len(task_names) and not isinstance(result, Exception):
                    results[task_names[i]] = result
                elif isinstance(result, Exception):
                    logger.error(f"Error en tarea {i}: {result}")
        
        return results
    
    # =====================================
    # 🎯 TAREAS ASÍNCRONAS INDIVIDUALES
    # =====================================
    
    async def _task_generate_image(self, message: str, parameters: Dict):
        """Tarea: Generar imagen"""
        try:
            prompt = self._extract_image_prompt(message)
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
    
    async def _task_edit_image(self, image_file, message: str, parameters: Dict):
        """Tarea: Editar imagen"""
        try:
            edit_type = self._determine_edit_type(message)
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
    
    async def _task_create_document(self, message: str, parameters: Dict, user_id: str):
        """Tarea: Crear documento"""
        try:
            topic = self._extract_document_topic(message)
            
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
    
    async def _task_analyze_image(self, image_file, message: str):
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
    
    async def _task_text_to_speech(self, message: str, parameters: Dict):
        """Tarea: Convertir a voz con Coqui TTS"""
        try:
            text_to_convert = self._extract_text_for_speech(message)
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
    
    async def _task_chat_with_ai(self, message: str, user_id: str, intent_analysis: Dict):
        """Tarea: Chat con IA"""
        try:
            # Enriquecer mensaje con contexto de las acciones que se están ejecutando
            context_message = self._add_execution_context(message, intent_analysis)
            
            result = await chat_with_ai(
                messages=[{"role": "user", "content": context_message}],
                user=user_id,
                friendly=True
            )
            logger.info("✅ Respuesta de chat generada")
            return result
        except Exception as e:
            logger.error(f"❌ Error en chat: {e}")
            return "Lo siento, hubo un problema generando la respuesta."
    
    # =====================================
    # 🧠 MÉTODOS DE IA INTELIGENTE
    # =====================================
    
    async def _ai_smart_detection(self, message: str) -> List[str]:
        """IA inteligente para detectar intenciones complejas"""
        try:
            detection_prompt = f"""
            Analiza este mensaje del usuario y detecta QUÉ QUIERE HACER:
            "{message}"
            
            Responde SOLO con intenciones separadas por comas de esta lista:
            - generate_image (si quiere crear/generar una imagen)
            - edit_image (si quiere editar/mejorar una imagen)
            - create_document (si quiere crear PDF/documento)
            - text_to_speech (si quiere convertir texto a voz)
            - analyze_image (si quiere analizar una imagen)
            - general_chat (conversación normal)
            
            Ejemplo: "generate_image, general_chat"
            """
            
            ai_response = await chat_with_ai(
                messages=[{"role": "user", "content": detection_prompt}],
                model=AI_MODEL
            )
            
            # Parsear respuesta de la IA
            intents = [intent.strip() for intent in ai_response.split(",")]
            valid_intents = [
                intent for intent in intents 
                if intent in ["generate_image", "edit_image", "create_document", 
                             "text_to_speech", "analyze_image", "general_chat"]
            ]
            
            return valid_intents
            
        except Exception as e:
            logger.error(f"Error en detección IA: {e}")
            return []
    
    async def _create_smart_response(
        self,
        intent_analysis: Dict,
        results: Dict,
        original_message: str
    ) -> str:
        """
        Crea respuesta inteligente que menciona todo lo que se generó automáticamente
        🚀 v4.0 - Con 17 capacidades
        """
        base_response = results.get("chat_response", "")
        
        # Agregar información sobre lo que se generó automáticamente
        auto_actions = []
        
        # Capacidades originales
        if results.get("generated_image"):
            auto_actions.append("🎨 He generado una imagen según tu solicitud")
        
        if results.get("edited_image"):
            auto_actions.append("✨ He editado la imagen que subiste")
        
        if results.get("document"):
            auto_actions.append("📄 He creado un documento sobre el tema")
        
        if results.get("image_analysis"):
            analysis = results["image_analysis"]
            auto_actions.append(f"👁️ He analizado la imagen: {analysis}")
        
        if results.get("audio"):
            auto_actions.append("🎵 He convertido el texto a audio")
        
        # Nuevas capacidades v4.0
        if results.get("detected_objects"):
            obj_count = len(results["detected_objects"].get("objects", []))
            auto_actions.append(f"🔍 He detectado {obj_count} objetos en la imagen")
        
        if results.get("detected_faces"):
            face_count = results["detected_faces"].get("face_count", 0)
            auto_actions.append(f"👤 He detectado {face_count} persona(s) en la imagen")
        
        if results.get("search_results"):
            result_count = len(results["search_results"].get("results", []))
            auto_actions.append(f"📚 He encontrado {result_count} resultados en tus documentos")
        
        if results.get("email_sent"):
            auto_actions.append("📧 He enviado el email automáticamente")
        
        if results.get("sync_result"):
            service = results["sync_result"].get("service", "servicio externo")
            auto_actions.append(f"☁️ He sincronizado el archivo con {service}")
        
        if results.get("translation"):
            lang = results["translation"].get("target_language", "otro idioma")
            auto_actions.append(f"🌐 He traducido el texto a {lang}")
        
        if results.get("summary"):
            ratio = results["summary"].get("compression_ratio", 0)
            auto_actions.append(f"📝 He resumido el texto ({ratio:.0%} del original)")
        
        if results.get("code"):
            language = results["code"].get("language", "código")
            auto_actions.append(f"💻 He generado código en {language}")
        
        if results.get("extracted_data"):
            field_count = len(results["extracted_data"].get("fields", []))
            auto_actions.append(f"📊 He extraído {field_count} campos de datos")
        
        if results.get("comparison"):
            auto_actions.append("🔍 He comparado los documentos")
        
        # Combinar respuesta
        if auto_actions:
            actions_text = "\n\n" + "\n".join(auto_actions)
            return base_response + actions_text
        
        return base_response
    
    # =====================================
    # 🔧 MÉTODOS AUXILIARES
    # =====================================
    
    def _extract_generated_content(self, results: Dict) -> Dict[str, Any]:
        """Extrae contenido generado para la respuesta"""
        content = {}
        
        if results.get("generated_image"):
            content["image"] = results["generated_image"]
        
        if results.get("edited_image"):
            content["edited_image"] = results["edited_image"]
        
        if results.get("document"):
            content["document"] = results["document"]
        
        if results.get("audio"):
            content["audio"] = results["audio"]
        
        return content
    
    def _extract_generated_files(self, results: Dict) -> List[Dict[str, Any]]:
        """Extrae archivos generados"""
        files = []
        
        if results.get("generated_image"):
            files.append({
                "type": "image",
                "data": results["generated_image"],
                "description": "Imagen generada automáticamente"
            })
        
        if results.get("edited_image"):
            files.append({
                "type": "image", 
                "data": results["edited_image"],
                "description": "Imagen editada automáticamente"
            })
        
        if results.get("document"):
            files.append({
                "type": "document",
                "data": results["document"],
                "description": "Documento creado automáticamente"
            })
        
        if results.get("audio"):
            files.append({
                "type": "audio",
                "data": results["audio"],
                "description": "Audio generado automáticamente"
            })
        
        return files
    
    def _create_execution_summary(self, results: Dict) -> str:
        """Crea resumen de ejecución"""
        actions = []
        
        if results.get("generated_image"):
            actions.append("Imagen generada")
        if results.get("edited_image"):
            actions.append("Imagen editada")
        if results.get("document"):
            actions.append("Documento creado")
        if results.get("image_analysis"):
            actions.append("Imagen analizada")
        if results.get("audio"):
            actions.append("Audio generado")
        if results.get("chat_response"):
            actions.append("Respuesta de chat")
        
        return f"Ejecutado automáticamente: {', '.join(actions)}" if actions else "Chat procesado"
    
    # Métodos auxiliares de extracción (mismos que antes)
    def _extract_image_prompt(self, message: str) -> str:
        prompt = re.sub(r'(crea|genera|haz|dibuja)\s+(una\s+)?imagen\s+(de\s+)?', '', message, flags=re.IGNORECASE)
        return prompt.strip() or "imagen artística"
    
    def _extract_document_topic(self, message: str) -> str:
        topic = re.sub(r'(crea|genera|haz)\s+(un\s+)?(pdf|documento)\s+(de\s+|del\s+|sobre\s+)?', '', message, flags=re.IGNORECASE)
        return topic.strip() or "documento informativo"
    
    def _extract_text_for_speech(self, message: str) -> str:
        text = re.sub(r'(convierte|lee|text to speech)\s+(esto\s+|este\s+texto\s*)?:?\s*', '', message, flags=re.IGNORECASE)
        return text.strip() or message
    
    def _determine_edit_type(self, message: str) -> str:
        message_lower = message.lower()
        if "mejora" in message_lower or "enhance" in message_lower:
            return "enhance"
        elif "blur" in message_lower:
            return "blur"
        else:
            return "ai_edit"
    
    def _extract_smart_parameters(self, message: str) -> Dict[str, Any]:
        parameters = {}
        
        # Dimensiones de imagen
        size_match = re.search(r'(\d+)x(\d+)', message)
        if size_match:
            parameters["width"] = int(size_match.group(1))
            parameters["height"] = int(size_match.group(2))
        
        # Formato de documento
        if "pdf" in message.lower():
            parameters["format"] = "pdf"
        elif "word" in message.lower() or "docx" in message.lower():
            parameters["format"] = "docx"
        
        # Idioma destino para traducción
        lang_match = re.search(r'(?:a|al|to)\s+(inglés|español|francés|alemán|italiano|portugués|english|spanish|french|german|italian|portuguese)', message, re.IGNORECASE)
        if lang_match:
            lang_map = {
                "inglés": "en", "english": "en",
                "español": "es", "spanish": "es",
                "francés": "fr", "french": "fr",
                "alemán": "de", "german": "de",
                "italiano": "it", "italian": "it",
                "portugués": "pt", "portuguese": "pt"
            }
            parameters["target_language"] = lang_map.get(lang_match.group(1).lower(), "en")
        
        # Lenguaje de programación
        code_lang_match = re.search(r'(?:en|in)\s+(python|javascript|java|c\+\+|ruby|go|rust|php|swift)', message, re.IGNORECASE)
        if code_lang_match:
            parameters["language"] = code_lang_match.group(1).lower()
        
        return parameters
    
    def _add_execution_context(self, message: str, intent_analysis: Dict) -> str:
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
    
    # ====================================
    # 🚀 NUEVAS TAREAS v4.0 (10 capacidades)
    # ====================================
    
    async def _task_detect_objects(self, image_file, message: str):
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
    
    async def _task_detect_faces(self, image_file, message: str):
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
    
    async def _task_search_documents(self, message: str, user_id: str):
        """Tarea: Buscar en documentos del usuario"""
        try:
            if not self.search:
                logger.warning("SearchService no disponible - usando fallback")
                return {"error": "Service not available", "fallback": True}
            
            query = self._extract_search_query(message)
            result = await self.search.search_user_documents(user_id, query)
            logger.info(f"✅ Búsqueda completada: {len(result.get('results', []))} resultados")
            return result
        except Exception as e:
            logger.error(f"❌ Error en búsqueda: {e}")
            return None
    
    async def _task_send_email(self, message: str, user_id: str):
        """Tarea: Enviar email automáticamente"""
        try:
            if not self.email:
                logger.warning("EmailService no disponible - usando fallback")
                return {"error": "Service not available", "fallback": True}
            
            email_data = self._extract_email_data(message)
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
    
    async def _task_sync_external(self, file, message: str, user_id: str):
        """Tarea: Sincronizar con servicio externo (Google/Microsoft/GitHub)"""
        try:
            if not self.integrations:
                logger.warning("IntegrationsService no disponible - usando fallback")
                return {"error": "Service not available", "fallback": True}
            
            service = self._extract_service_type(message)
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
    
    async def _task_translate_text(self, message: str, parameters: Dict):
        """Tarea: Traducir texto a otro idioma"""
        try:
            target_lang = parameters.get("target_language", "en")
            text_to_translate = self._extract_translation_text(message)
            
            # Usar DeepSeek-VL para traducción
            prompt = f"Traduce el siguiente texto a {target_lang}:\n\n{text_to_translate}\n\nResponde SOLO con la traducción, sin explicaciones."
            translation = await chat_with_ai(
                messages=[{"role": "user", "content": prompt}],
                fast_reasoning=True
            )
            
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
    
    async def _task_summarize_text(self, message: str, files: Optional[List]):
        """Tarea: Resumir texto o documento"""
        try:
            # Si hay archivo, leer contenido
            if files:
                text_to_summarize = await self._extract_text_from_file(files[0])
            else:
                text_to_summarize = message
            
            # Usar DeepSeek-VL para resumir
            prompt = f"Resume el siguiente texto en 5 puntos clave:\n\n{text_to_summarize}\n\nResponde SOLO con el resumen en formato de lista."
            summary = await chat_with_ai(
                messages=[{"role": "user", "content": prompt}],
                fast_reasoning=True
            )
            
            result = {
                "original_length": len(text_to_summarize),
                "summary": summary,
                "compression_ratio": len(summary) / len(text_to_summarize)
            }
            
            logger.info(f"✅ Texto resumido: {result['compression_ratio']:.1%} del original")
            return result
        except Exception as e:
            logger.error(f"❌ Error resumiendo: {e}")
            return None
    
    async def _task_generate_code(self, message: str, parameters: Dict):
        """Tarea: Generar código en lenguaje especificado"""
        try:
            language = parameters.get("language", "python")
            code_request = self._extract_code_request(message)
            
            # Usar DeepSeek-VL para generar código
            prompt = f"Genera código en {language} para: {code_request}\n\nResponde SOLO con el código, sin explicaciones."
            code = await chat_with_ai(
                messages=[{"role": "user", "content": prompt}],
                fast_reasoning=True
            )
            
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
    
    async def _task_extract_data(self, file, message: str):
        """Tarea: Extraer datos de imagen/documento (OCR mejorado)"""
        try:
            # Usar VisionPipeline para OCR mejorado
            result = await self.vision.extract_structured_data(file)
            
            logger.info(f"✅ Datos extraídos: {len(result.get('fields', []))} campos")
            return result
        except Exception as e:
            logger.error(f"❌ Error extrayendo datos: {e}")
            return None
    
    async def _task_compare_documents(self, file1, file2, message: str):
        """Tarea: Comparar dos documentos"""
        try:
            # Extraer texto de ambos documentos
            text1 = await self._extract_text_from_file(file1)
            text2 = await self._extract_text_from_file(file2)
            
            # Usar DeepSeek-VL para comparar
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
    
    # ====================================
    # 🔧 MÉTODOS AUXILIARES NUEVOS
    # ====================================
    
    def _extract_search_query(self, message: str) -> str:
        """Extrae query de búsqueda del mensaje"""
        query = re.sub(r'busca\s+(?:en\s+)?(?:mis\s+)?documentos\s+(?:sobre\s+)?', '', message, flags=re.IGNORECASE)
        return query.strip() or message
    
    def _extract_email_data(self, message: str) -> Dict[str, str]:
        """Extrae datos de email del mensaje"""
        # Extraer email destino
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', message)
        to = email_match.group(0) if email_match else "support@example.com"
        
        # Extraer asunto (simplificado)
        subject_match = re.search(r'(?:con|sobre|about)\s+(.+)', message, re.IGNORECASE)
        subject = subject_match.group(1) if subject_match else "Mensaje automático"
        
        return {
            "to": to,
            "subject": subject[:100],
            "body": message
        }
    
    def _extract_service_type(self, message: str) -> str:
        """Extrae tipo de servicio externo"""
        message_lower = message.lower()
        if "google" in message_lower or "drive" in message_lower:
            return "google"
        elif "microsoft" in message_lower or "onedrive" in message_lower:
            return "microsoft"
        elif "github" in message_lower:
            return "github"
        return "google"  # default
    
    def _extract_translation_text(self, message: str) -> str:
        """Extrae texto a traducir"""
        text = re.sub(r'traduce\s+(?:a|al)\s+\w+\s*:?\s*', '', message, flags=re.IGNORECASE)
        return text.strip() or message
    
    def _extract_code_request(self, message: str) -> str:
        """Extrae solicitud de código"""
        request = re.sub(r'genera\s+código\s+(?:en\s+\w+\s+)?(?:para\s+)?', '', message, flags=re.IGNORECASE)
        return request.strip() or message
    
    async def _extract_text_from_file(self, file) -> str:
        """Extrae texto de archivo (PDF, DOCX, TXT, imagen con OCR)"""
        try:
            # Si es imagen, usar OCR
            if hasattr(file, 'content_type') and file.content_type.startswith('image/'):
                ocr_result = await self.vision.extract_text(file)
                return ocr_result.get('text', '')
            
            # Si es texto plano
            if hasattr(file, 'read'):
                content = await file.read()
                return content.decode('utf-8')
            
            return str(file)
        except Exception as e:
            logger.error(f"Error extrayendo texto de archivo: {e}")
            return ""

# Instancia global empresarial
master_chat_service = MasterChatServiceEnterprise()