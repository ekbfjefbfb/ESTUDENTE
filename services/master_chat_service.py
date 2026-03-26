"""
Master Chat Service Enterprise v5.0 - Refactored
IA que detecta y ejecuta automáticamente - Optimizado para multiusuario y alta carga

Responsabilidades separadas:
- master_chat_patterns.py: Patrones de detección
- master_chat_intent.py: Detección de intenciones  
- master_chat_tasks_core.py: Tareas core (7 capacidades)
- master_chat_tasks_v4.py: Tareas v4.0 (10 capacidades)
- master_chat_response.py: Creación de respuestas
- master_chat_utils.py: Utilidades de extracción

Este archivo es el ORQUESTADOR que coordina todo.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from config import AI_MODEL
import json_log_formatter
from utils.safe_metrics import Counter, Histogram

# Importar servicios empresariales optimizados
from services.groq_ai_service import chat_with_ai, sanitize_ai_text
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
# IMPORTAR MÓDULOS REFACTORIZADOS
# =============================================
from services.master_chat_intent import detect_intentions
from services.master_chat_tasks_core import CoreTaskHandlers
from services.master_chat_tasks_v4 import V4TaskHandlers
from services.master_chat_response import (
    create_smart_response, extract_generated_content,
    extract_generated_files, create_execution_summary
)
from services.master_chat_patterns import get_intent_display_name

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
    
    v5.0: Refactorizada - ahora delega a módulos especializados
    """
    
    def __init__(self):
        # ====================================
        # SERVICIOS EMPRESARIALES ORIGINALES
        # ====================================
        self.stability = StabilityService()
        self.image_editor = ImageEditService()
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
        
        # ====================================
        # HANDLERS DE TAREAS (MÓDULOS REFACTORIZADOS)
        # ====================================
        self.core_tasks = CoreTaskHandlers(
            stability_service=self.stability,
            image_editor=self.image_editor,
            document_service=self.document,
            internet_reports=self.internet_reports,
            voice_engine=self.voice_engine,
            vision_service=self.vision
        )
        
        self.v4_tasks = V4TaskHandlers(
            computer_vision=self.computer_vision,
            search_service=self.search,
            email_service=self.email,
            integrations_service=self.integrations,
            vision_service=self.vision
        )
        
        # Semáforo para limitar concurrencia
        self._concurrency_limit = asyncio.Semaphore(50)
        
        logger.info("🚀 Master Chat Service Enterprise v5.0 inicializado")
    
    async def process_unified_request(
        self,
        message: str,
        user_id: str,
        files: Optional[List] = None,
        auto_generation: bool = True
    ) -> Dict[str, Any]:
        """Procesa mensaje multiusuario y EJECUTA AUTOMÁTICAMENTE"""
        async with self._concurrency_limit:
            start_time = datetime.utcnow()
            
            try:
                # Métricas inicio
                MASTER_CHAT_REQUESTS.labels(
                    user_id=user_id[:8] if user_id else "anon",
                    intent_type="processing",
                    status="started"
                ).inc()
                
                # 1. DETECCIÓN AUTOMÁTICA (delegado a módulo)
                intent_analysis = await detect_intentions(message, files)
                
                logger.info({
                    "event": "intent_detected",
                    "user_id": user_id,
                    "intents": intent_analysis.get("intents", [])
                })
                
                # 2. EJECUCIÓN EN PARALELO
                results = await self._execute_all_tasks(
                    intent_analysis, message, user_id, files
                )
                
                # 3. RESPUESTA UNIFICADA (delegado a módulo)
                unified_response = create_smart_response(
                    intent_analysis, results, message
                )
                
                # 4. Métricas
                processing_time = (datetime.utcnow() - start_time).total_seconds()
                MASTER_CHAT_PROCESSING_TIME.observe(processing_time)
                MASTER_CHAT_REQUESTS.labels(
                    user_id=user_id[:8] if user_id else "anon",
                    intent_type="success",
                    status="completed"
                ).inc()
                
                return {
                    "response": unified_response,
                    "generated_content": extract_generated_content(results),
                    "files": extract_generated_files(results),
                    "intent": intent_analysis,
                    "summary": create_execution_summary(results),
                    "processing_time": processing_time
                }
                
            except Exception as e:
                processing_time = (datetime.utcnow() - start_time).total_seconds()
                MASTER_CHAT_REQUESTS.labels(
                    user_id=user_id[:8] if user_id else "anon",
                    intent_type="error",
                    status="failed"
                ).inc()
                
                logger.error({"event": "request_error", "user_id": user_id, "error": str(e)})
                
                # Fallback
                fallback = await chat_with_ai(
                    messages=[{"role": "user", "content": message}],
                    user=user_id,
                    fast_reasoning=True
                )
                
                return {
                    "response": sanitize_ai_text(fallback),
                    "generated_content": {},
                    "files": [],
                    "error": str(e),
                    "fallback": True,
                    "processing_time": processing_time
                }
    
    async def _execute_all_tasks(
        self,
        intent_analysis: Dict,
        message: str,
        user_id: str,
        files: Optional[List]
    ) -> Dict[str, Any]:
        """EJECUTA AUTOMÁTICAMENTE todos los servicios detectados"""
        tasks = []
        task_names = []
        
        intents = intent_analysis["intents"]
        parameters = intent_analysis["parameters"]
        
        # 🎨 CAPACIDADES CORE (7)
        if "generate_image" in intents:
            tasks.append(self.core_tasks.task_generate_image(message, parameters))
            task_names.append("generated_image")
        
        if "edit_image" in intents and files:
            tasks.append(self.core_tasks.task_edit_image(files[0], message, parameters))
            task_names.append("edited_image")
        
        if "create_document" in intents:
            tasks.append(self.core_tasks.task_create_document(message, parameters, user_id))
            task_names.append("document")
        
        if "analyze_image" in intents and files:
            tasks.append(self.core_tasks.task_analyze_image(files[0], message))
            task_names.append("image_analysis")
        
        if "text_to_speech" in intents:
            tasks.append(self.core_tasks.task_text_to_speech(message, parameters))
            task_names.append("audio")
        
        # 🚀 CAPACIDADES v4.0 (10)
        if "detect_objects" in intents and files:
            tasks.append(self.v4_tasks.task_detect_objects(files[0], message))
            task_names.append("detected_objects")
        
        if "detect_faces" in intents and files:
            tasks.append(self.v4_tasks.task_detect_faces(files[0], message))
            task_names.append("detected_faces")
        
        if "search_documents" in intents:
            tasks.append(self.v4_tasks.task_search_documents(message, user_id))
            task_names.append("search_results")
        
        if "send_email" in intents:
            tasks.append(self.v4_tasks.task_send_email(message, user_id))
            task_names.append("email_sent")
        
        if "sync_external" in intents and files:
            tasks.append(self.v4_tasks.task_sync_external(files[0], message, user_id))
            task_names.append("sync_result")
        
        if "translate_text" in intents:
            tasks.append(self.v4_tasks.task_translate_text(message, parameters))
            task_names.append("translation")
        
        if "summarize_text" in intents:
            tasks.append(self.v4_tasks.task_summarize_text(message, files))
            task_names.append("summary")
        
        if "generate_code" in intents:
            tasks.append(self.v4_tasks.task_generate_code(message, parameters))
            task_names.append("code")
        
        if "extract_data" in intents and files:
            tasks.append(self.v4_tasks.task_extract_data(files[0], message))
            task_names.append("extracted_data")
        
        if "compare_documents" in intents and files and len(files) >= 2:
            tasks.append(self.v4_tasks.task_compare_documents(files[0], files[1], message))
            task_names.append("comparison")
        
        # CHAT CON IA
        if "general_chat" in intents:
            tasks.append(self.core_tasks.task_chat_with_ai(message, user_id, intent_analysis))
            task_names.append("chat_response")
        
        # Ejecutar en paralelo
        results = {}
        if tasks:
            task_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(task_results):
                if i < len(task_names) and not isinstance(result, Exception):
                    results[task_names[i]] = result
                elif isinstance(result, Exception):
                    logger.error(f"Error en tarea {task_names[i]}: {result}")
        
        return results


# Instancia global
master_chat_service = MasterChatServiceEnterprise()
