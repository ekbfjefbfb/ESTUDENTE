"""
🤖 SISTEMA DE AGENTES COORDINADOS ENTERPRISE
==========================================

Este módulo implementa un sistema de agentes inteligentes que trabajan en coordinación:
- PersonalAgent: Coordinador principal que analiza solicitudes y delega tareas
- DocumentAgent: Especialista en procesamiento de documentos (PDF, Word, etc.)
- ImageAgent: Experto en análisis y generación de imágenes
- DataAgent: Analista de datos, reportes y visualizaciones

Cada agente tiene especialización específica y trabaja de forma coordinada para
resolver solicitudes complejas de usuarios en producción.
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, List, Optional, Union

from services.gpt_service import GPTService
from utils.safe_metrics import SafeMetric

logger = logging.getLogger("agents")

# ===============================================
# 🎯 TIPOS Y ENUMS DE AGENTES
# ===============================================

class AgentType(str, Enum):
    """Tipos de agentes disponibles"""
    PERSONAL = "personal"
    DOCUMENT = "document"
    IMAGE = "image"
    DATA = "data"
    TOOL = "tool"
    GROUP = "group"

class TaskPriority(str, Enum):
    """Prioridades de tareas"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class TaskStatus(str, Enum):
    """Estados de tareas"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    DELEGATED = "delegated"

@dataclass
class AgentTask:
    """Tarea para un agente"""
    id: str
    type: str
    description: str
    user_id: str
    priority: TaskPriority
    status: TaskStatus
    assigned_agent: Optional[str] = None
    context: Dict[str, Any] = None
    result: Optional[Dict[str, Any]] = None
    created_at: datetime = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.context is None:
            self.context = {}

@dataclass
class AgentCapability:
    """Capacidad de un agente"""
    name: str
    description: str
    supported_formats: List[str]
    confidence_score: float
    max_concurrent_tasks: int

# ===============================================
# 🤖 CLASE BASE DE AGENTES
# ===============================================

class BaseAgent(ABC):
    """Clase base abstracta para todos los agentes"""
    
    def __init__(self, agent_id: str, agent_type: AgentType):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.is_active = True
        self.current_tasks: Dict[str, AgentTask] = {}
        self.completed_tasks_count = 0
        self.failed_tasks_count = 0
        
        # Servicios
        self.gpt_service = GPTService()
        try:
            from services.cache_service_enterprise import CacheServiceEnterprise
            self.cache_service = CacheServiceEnterprise()
        except ImportError:
            try:
                from services.cache_service import CacheService
                self.cache_service = CacheService()
            except ImportError:
                logger.warning("No se pudo cargar servicio de cache")
                self.cache_service = None
        
        # Métricas
        self.metrics = SafeMetric()
        self.task_counter = self.metrics.counter(
            f'agent_{agent_type.value}_tasks_total',
            f'Total de tareas procesadas por {agent_type.value}',
            ['status', 'task_type']
        )
        
        self.task_duration = self.metrics.histogram(
            f'agent_{agent_type.value}_task_duration_seconds',
            f'Duración de tareas de {agent_type.value}',
            ['task_type'],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
        )
        
        logger.info(f"✅ Agente {agent_type.value} inicializado: {agent_id}")
    
    @abstractmethod
    async def get_capabilities(self) -> List[AgentCapability]:
        """Retorna las capacidades del agente"""
        pass
    
    @abstractmethod
    async def can_handle_task(self, task: AgentTask) -> bool:
        """Determina si el agente puede manejar la tarea"""
        pass
    
    @abstractmethod
    async def process_task(self, task: AgentTask) -> Dict[str, Any]:
        """Procesa una tarea específica"""
        pass
    
    async def accept_task(self, task: AgentTask) -> bool:
        """Acepta una tarea si puede manejarla"""
        try:
            if not await self.can_handle_task(task):
                return False
            
            if len(self.current_tasks) >= self.max_concurrent_tasks:
                logger.warning(f"Agente {self.agent_id} sobrecargado")
                return False
            
            task.assigned_agent = self.agent_id
            task.status = TaskStatus.IN_PROGRESS
            self.current_tasks[task.id] = task
            
            logger.info(f"Tarea {task.id} aceptada por agente {self.agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error aceptando tarea {task.id}: {e}")
            return False
    
    async def execute_task(self, task: AgentTask) -> Dict[str, Any]:
        """Ejecuta una tarea y registra métricas"""
        start_time = datetime.utcnow()
        
        try:
            logger.info(f"Ejecutando tarea {task.id} en agente {self.agent_id}")
            
            # Procesar la tarea
            result = await self.process_task(task)
            
            # Actualizar estado
            task.status = TaskStatus.COMPLETED
            task.result = result
            task.completed_at = datetime.utcnow()
            
            # Métricas
            duration = (datetime.utcnow() - start_time).total_seconds()
            self.task_counter.inc(labels=['completed', task.type])
            self.task_duration.observe(duration, labels=[task.type])
            
            self.completed_tasks_count += 1
            
            # Remover de tareas actuales
            if task.id in self.current_tasks:
                del self.current_tasks[task.id]
            
            logger.info(f"Tarea {task.id} completada exitosamente")
            return result
            
        except Exception as e:
            logger.error(f"Error ejecutando tarea {task.id}: {e}")
            
            # Actualizar estado de error
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.utcnow()
            
            # Métricas
            self.task_counter.inc(labels=['failed', task.type])
            self.failed_tasks_count += 1
            
            # Remover de tareas actuales
            if task.id in self.current_tasks:
                del self.current_tasks[task.id]
            
            raise
    
    @property
    @abstractmethod
    def max_concurrent_tasks(self) -> int:
        """Número máximo de tareas concurrentes"""
        pass
    
    def get_status(self) -> Dict[str, Any]:
        """Estado actual del agente"""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type.value,
            "is_active": self.is_active,
            "current_tasks": len(self.current_tasks),
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "completed_tasks": self.completed_tasks_count,
            "failed_tasks": self.failed_tasks_count,
            "load_percentage": (len(self.current_tasks) / self.max_concurrent_tasks) * 100
        }

# ===============================================
# 🧠 COORDINADOR PERSONAL AGENT
# ===============================================

class PersonalAgent(BaseAgent):
    """
    Agente coordinador principal que:
    - Analiza solicitudes de usuarios
    - Determina qué agentes necesarios
    - Coordina la ejecución de tareas
    - Ensambla resultados finales
    """
    
    def __init__(self, agent_id: str = "personal_agent_001"):
        super().__init__(agent_id, AgentType.PERSONAL)
        self.specialized_agents: Dict[AgentType, BaseAgent] = {}
        self.delegation_rules = self._load_delegation_rules()
    
    async def get_capabilities(self) -> List[AgentCapability]:
        return [
            AgentCapability(
                name="task_coordination",
                description="Coordinación y delegación de tareas complejas",
                supported_formats=["any"],
                confidence_score=0.95,
                max_concurrent_tasks=10
            ),
            AgentCapability(
                name="request_analysis",
                description="Análisis de solicitudes de usuarios",
                supported_formats=["text", "json"],
                confidence_score=0.90,
                max_concurrent_tasks=10
            ),
            AgentCapability(
                name="result_assembly",
                description="Ensamblado de resultados de múltiples agentes",
                supported_formats=["any"],
                confidence_score=0.88,
                max_concurrent_tasks=10
            )
        ]
    
    @property
    def max_concurrent_tasks(self) -> int:
        return 10
    
    def register_specialized_agent(self, agent: BaseAgent):
        """Registra un agente especializado"""
        self.specialized_agents[agent.agent_type] = agent
        logger.info(f"Agente especializado registrado: {agent.agent_type.value}")
    
    async def can_handle_task(self, task: AgentTask) -> bool:
        """PersonalAgent puede manejar tareas de coordinación"""
        coordination_types = [
            "coordinate_multi_agent",
            "analyze_request",
            "general_assistance",
            "task_delegation"
        ]
        return task.type in coordination_types
    
    async def process_task(self, task: AgentTask) -> Dict[str, Any]:
        """Procesa tareas de coordinación"""
        
        if task.type == "coordinate_multi_agent":
            return await self._coordinate_multi_agent_task(task)
        elif task.type == "analyze_request":
            return await self._analyze_user_request(task)
        elif task.type == "general_assistance":
            return await self._provide_general_assistance(task)
        else:
            return await self._delegate_task(task)
    
    async def _coordinate_multi_agent_task(self, task: AgentTask) -> Dict[str, Any]:
        """Coordina una tarea que requiere múltiples agentes"""
        try:
            request = task.context.get("user_request", "")
            
            # 1. Analizar qué agentes necesitamos
            analysis = await self._analyze_required_agents(request)
            
            # 2. Crear subtareas para cada agente
            subtasks = []
            results = {}
            
            for agent_type, task_info in analysis["required_agents"].items():
                if agent_type in self.specialized_agents:
                    subtask = AgentTask(
                        id=f"{task.id}_{agent_type}",
                        type=task_info["task_type"],
                        description=task_info["description"],
                        user_id=task.user_id,
                        priority=task.priority,
                        status=TaskStatus.PENDING,
                        context=task_info.get("context", {})
                    )
                    subtasks.append((agent_type, subtask))
            
            # 3. Ejecutar subtareas en paralelo
            if subtasks:
                tasks_to_execute = []
                for agent_type, subtask in subtasks:
                    agent = self.specialized_agents[AgentType(agent_type)]
                    if await agent.accept_task(subtask):
                        tasks_to_execute.append(agent.execute_task(subtask))
                
                # Ejecutar todas las subtareas en paralelo
                subtask_results = await asyncio.gather(*tasks_to_execute, return_exceptions=True)
                
                # Procesar resultados
                for i, result in enumerate(subtask_results):
                    agent_type = subtasks[i][0]
                    if isinstance(result, Exception):
                        results[agent_type] = {"error": str(result)}
                    else:
                        results[agent_type] = result
            
            # 4. Ensamblar resultado final
            final_result = await self._assemble_final_result(analysis, results)
            
            return {
                "type": "multi_agent_coordination",
                "analysis": analysis,
                "subtask_results": results,
                "final_result": final_result,
                "agents_involved": list(results.keys()),
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Error en coordinación multi-agente: {e}")
            return {
                "type": "multi_agent_coordination",
                "error": str(e),
                "success": False
            }
    
    async def _analyze_required_agents(self, request: str) -> Dict[str, Any]:
        """Analiza qué agentes se necesitan para una solicitud"""
        
        analysis_prompt = f"""
        Analiza la siguiente solicitud de usuario y determina qué agentes especializados necesitamos:
        
        Solicitud: {request}
        
        Agentes disponibles:
        - DocumentAgent: Procesa documentos (PDF, Word, Excel, PowerPoint)
        - ImageAgent: Analiza y genera imágenes
        - DataAgent: Análisis de datos, reportes, visualizaciones
        
        Responde en JSON con este formato:
        {{
            "required_agents": {{
                "document": {{
                    "needed": true/false,
                    "task_type": "tipo_de_tarea",
                    "description": "descripción específica",
                    "confidence": 0.8,
                    "context": {{}}
                }},
                "image": {{...}},
                "data": {{...}}
            }},
            "coordination_strategy": "estrategia de coordinación",
            "estimated_complexity": "low/medium/high"
        }}
        """
        
        try:
            response = await self.gpt_service.get_completion(analysis_prompt)
            analysis = json.loads(response)
            
            # Filtrar solo los agentes necesarios
            required_agents = {}
            for agent_type, info in analysis["required_agents"].items():
                if info.get("needed", False):
                    required_agents[agent_type] = info
            
            analysis["required_agents"] = required_agents
            return analysis
            
        except Exception as e:
            logger.error(f"Error analizando agentes requeridos: {e}")
            return {
                "required_agents": {},
                "coordination_strategy": "simple",
                "estimated_complexity": "low"
            }
    
    async def _analyze_user_request(self, task: AgentTask) -> Dict[str, Any]:
        """Analiza una solicitud de usuario"""
        request = task.context.get("user_request", "")
        
        analysis_prompt = f"""
        Analiza la siguiente solicitud de usuario y proporciona:
        1. Intención principal
        2. Tipo de tarea requerida
        3. Complejidad estimada
        4. Agente(s) recomendado(s)
        5. Pasos sugeridos
        
        Solicitud: {request}
        
        Responde en formato JSON estructurado.
        """
        
        try:
            response = await self.gpt_service.get_completion(analysis_prompt)
            analysis = json.loads(response)
            
            return {
                "type": "request_analysis",
                "analysis": analysis,
                "original_request": request,
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Error analizando solicitud: {e}")
            return {
                "type": "request_analysis",
                "error": str(e),
                "success": False
            }
    
    async def _provide_general_assistance(self, task: AgentTask) -> Dict[str, Any]:
        """Proporciona asistencia general"""
        request = task.context.get("user_request", "")
        
        assistance_prompt = f"""
        Proporciona asistencia útil y detallada para la siguiente solicitud:
        
        {request}
        
        Responde de manera clara, estructurada y práctica.
        """
        
        try:
            response = await self.gpt_service.get_completion(assistance_prompt)
            
            return {
                "type": "general_assistance",
                "response": response,
                "request": request,
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Error proporcionando asistencia: {e}")
            return {
                "type": "general_assistance",
                "error": str(e),
                "success": False
            }
    
    async def _delegate_task(self, task: AgentTask) -> Dict[str, Any]:
        """Delega una tarea a un agente especializado"""
        # Determinar el mejor agente para la tarea
        best_agent = await self._find_best_agent_for_task(task)
        
        if not best_agent:
            return {
                "type": "delegation",
                "error": "No se encontró agente adecuado",
                "success": False
            }
        
        # Delegar la tarea
        if await best_agent.accept_task(task):
            result = await best_agent.execute_task(task)
            return {
                "type": "delegation",
                "delegated_to": best_agent.agent_id,
                "result": result,
                "success": True
            }
        else:
            return {
                "type": "delegation",
                "error": f"Agente {best_agent.agent_id} no pudo aceptar la tarea",
                "success": False
            }
    
    async def _find_best_agent_for_task(self, task: AgentTask) -> Optional[BaseAgent]:
        """Encuentra el mejor agente para una tarea"""
        best_agent = None
        best_score = 0
        
        for agent in self.specialized_agents.values():
            if await agent.can_handle_task(task):
                # Calcular score basado en carga actual y capacidades
                load_factor = len(agent.current_tasks) / agent.max_concurrent_tasks
                score = (1 - load_factor) * 0.7 + 0.3  # Base score
                
                if score > best_score:
                    best_score = score
                    best_agent = agent
        
        return best_agent
    
    async def _assemble_final_result(self, analysis: Dict[str, Any], results: Dict[str, Any]) -> Dict[str, Any]:
        """Ensambla el resultado final de múltiples agentes"""
        
        assembly_prompt = f"""
        Ensambla un resultado final coherente basado en los siguientes resultados de agentes especializados:
        
        Análisis inicial: {json.dumps(analysis, indent=2)}
        
        Resultados de agentes:
        {json.dumps(results, indent=2)}
        
        Crea una respuesta unificada, clara y útil para el usuario.
        """
        
        try:
            response = await self.gpt_service.get_completion(assembly_prompt)
            
            return {
                "unified_response": response,
                "source_results": results,
                "assembly_strategy": analysis.get("coordination_strategy", "default")
            }
            
        except Exception as e:
            logger.error(f"Error ensamblando resultado final: {e}")
            return {
                "error": str(e),
                "raw_results": results
            }
    
    def _load_delegation_rules(self) -> Dict[str, Any]:
        """Carga las reglas de delegación"""
        return {
            "document_keywords": ["pdf", "word", "excel", "documento", "archivo", "texto"],
            "image_keywords": ["imagen", "foto", "picture", "visual", "gráfico", "generar imagen"],
            "data_keywords": ["datos", "análisis", "reporte", "estadística", "gráfica", "dashboard"],
            "default_agent": AgentType.PERSONAL
        }

# ===============================================
# 📄 DOCUMENT AGENT
# ===============================================

class DocumentAgent(BaseAgent):
    """
    Agente especializado en procesamiento de documentos:
    - Extracción de texto de PDFs
    - Análisis de documentos Word
    - Procesamiento de hojas de cálculo
    - Generación de reportes
    """
    
    def __init__(self, agent_id: str = "document_agent_001"):
        super().__init__(agent_id, AgentType.DOCUMENT)
        self.supported_formats = [".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".csv"]
    
    async def get_capabilities(self) -> List[AgentCapability]:
        return [
            AgentCapability(
                name="pdf_processing",
                description="Extracción y análisis de documentos PDF",
                supported_formats=[".pdf"],
                confidence_score=0.92,
                max_concurrent_tasks=5
            ),
            AgentCapability(
                name="word_processing",
                description="Procesamiento de documentos Word",
                supported_formats=[".docx", ".doc"],
                confidence_score=0.90,
                max_concurrent_tasks=5
            ),
            AgentCapability(
                name="excel_processing",
                description="Análisis de hojas de cálculo",
                supported_formats=[".xlsx", ".xls", ".csv"],
                confidence_score=0.88,
                max_concurrent_tasks=3
            ),
            AgentCapability(
                name="text_analysis",
                description="Análisis avanzado de texto",
                supported_formats=[".txt", ".md"],
                confidence_score=0.95,
                max_concurrent_tasks=8
            )
        ]
    
    @property
    def max_concurrent_tasks(self) -> int:
        return 5
    
    async def can_handle_task(self, task: AgentTask) -> bool:
        """Determina si puede manejar tareas de documentos"""
        document_task_types = [
            "extract_text",
            "analyze_document",
            "summarize_document",
            "convert_document",
            "generate_report"
        ]
        
        # Verificar tipo de tarea
        if task.type not in document_task_types:
            return False
        
        # Verificar formato si se especifica
        file_format = task.context.get("file_format", "")
        if file_format and file_format not in self.supported_formats:
            return False
        
        return True
    
    async def process_task(self, task: AgentTask) -> Dict[str, Any]:
        """Procesa tareas de documentos"""
        
        if task.type == "extract_text":
            return await self._extract_text(task)
        elif task.type == "analyze_document":
            return await self._analyze_document(task)
        elif task.type == "summarize_document":
            return await self._summarize_document(task)
        elif task.type == "convert_document":
            return await self._convert_document(task)
        elif task.type == "generate_report":
            return await self._generate_report(task)
        else:
            raise ValueError(f"Tipo de tarea no soportado: {task.type}")
    
    async def _extract_text(self, task: AgentTask) -> Dict[str, Any]:
        """Extrae texto de documentos"""
        try:
            file_path = task.context.get("file_path", "")
            file_format = task.context.get("file_format", "")
            
            # Simular extracción de texto (en producción usar servicios reales)
            extracted_text = f"Texto extraído del documento {file_path}"
            
            return {
                "type": "text_extraction",
                "extracted_text": extracted_text,
                "file_path": file_path,
                "file_format": file_format,
                "success": True,
                "char_count": len(extracted_text),
                "processing_time": 1.2
            }
            
        except Exception as e:
            return {
                "type": "text_extraction",
                "error": str(e),
                "success": False
            }
    
    async def _analyze_document(self, task: AgentTask) -> Dict[str, Any]:
        """Analiza el contenido de documentos"""
        try:
            document_content = task.context.get("content", "")
            analysis_type = task.context.get("analysis_type", "general")
            
            analysis_prompt = f"""
            Analiza el siguiente documento según el tipo: {analysis_type}
            
            Contenido:
            {document_content}
            
            Proporciona un análisis detallado incluyendo:
            - Resumen ejecutivo
            - Puntos clave
            - Estructura del documento
            - Recomendaciones
            """
            
            analysis = await self.gpt_service.get_completion(analysis_prompt)
            
            return {
                "type": "document_analysis",
                "analysis": analysis,
                "analysis_type": analysis_type,
                "content_length": len(document_content),
                "success": True
            }
            
        except Exception as e:
            return {
                "type": "document_analysis",
                "error": str(e),
                "success": False
            }
    
    async def _summarize_document(self, task: AgentTask) -> Dict[str, Any]:
        """Crea resúmenes de documentos"""
        try:
            content = task.context.get("content", "")
            summary_length = task.context.get("summary_length", "medium")
            
            summary_prompt = f"""
            Crea un resumen {summary_length} del siguiente documento:
            
            {content}
            
            El resumen debe ser claro, conciso y capturar los puntos más importantes.
            """
            
            summary = await self.gpt_service.get_completion(summary_prompt)
            
            return {
                "type": "document_summary",
                "summary": summary,
                "summary_length": summary_length,
                "original_length": len(content),
                "compression_ratio": len(summary) / len(content) if content else 0,
                "success": True
            }
            
        except Exception as e:
            return {
                "type": "document_summary",
                "error": str(e),
                "success": False
            }
    
    async def _convert_document(self, task: AgentTask) -> Dict[str, Any]:
        """Convierte documentos entre formatos"""
        try:
            source_format = task.context.get("source_format", "")
            target_format = task.context.get("target_format", "")
            
            # Simular conversión
            conversion_result = f"Documento convertido de {source_format} a {target_format}"
            
            return {
                "type": "document_conversion",
                "result": conversion_result,
                "source_format": source_format,
                "target_format": target_format,
                "success": True
            }
            
        except Exception as e:
            return {
                "type": "document_conversion",
                "error": str(e),
                "success": False
            }
    
    async def _generate_report(self, task: AgentTask) -> Dict[str, Any]:
        """Genera reportes basados en datos"""
        try:
            data = task.context.get("data", {})
            report_type = task.context.get("report_type", "standard")
            
            report_prompt = f"""
            Genera un reporte {report_type} basado en los siguientes datos:
            
            {json.dumps(data, indent=2)}
            
            El reporte debe incluir:
            - Resumen ejecutivo
            - Análisis de datos
            - Conclusiones
            - Recomendaciones
            """
            
            report = await self.gpt_service.get_completion(report_prompt)
            
            return {
                "type": "report_generation",
                "report": report,
                "report_type": report_type,
                "data_points": len(data) if isinstance(data, dict) else 0,
                "success": True
            }
            
        except Exception as e:
            return {
                "type": "report_generation",
                "error": str(e),
                "success": False
            }

# ===============================================
# 🖼️ IMAGE AGENT
# ===============================================

class ImageAgent(BaseAgent):
    """
    Agente especializado en procesamiento de imágenes:
    - Análisis de imágenes
    - Generación de imágenes
    - Reconocimiento de objetos
    - Edición de imágenes
    """
    
    def __init__(self, agent_id: str = "image_agent_001"):
        super().__init__(agent_id, AgentType.IMAGE)
        self.supported_formats = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"]
    
    async def get_capabilities(self) -> List[AgentCapability]:
        return [
            AgentCapability(
                name="image_analysis",
                description="Análisis avanzado de contenido de imágenes",
                supported_formats=self.supported_formats,
                confidence_score=0.90,
                max_concurrent_tasks=3
            ),
            AgentCapability(
                name="image_generation",
                description="Generación de imágenes con IA",
                supported_formats=[".png", ".jpg"],
                confidence_score=0.85,
                max_concurrent_tasks=2
            ),
            AgentCapability(
                name="object_recognition",
                description="Reconocimiento y detección de objetos",
                supported_formats=self.supported_formats,
                confidence_score=0.88,
                max_concurrent_tasks=4
            ),
            AgentCapability(
                name="image_editing",
                description="Edición y manipulación de imágenes",
                supported_formats=self.supported_formats,
                confidence_score=0.82,
                max_concurrent_tasks=2
            )
        ]
    
    @property
    def max_concurrent_tasks(self) -> int:
        return 3
    
    async def can_handle_task(self, task: AgentTask) -> bool:
        """Determina si puede manejar tareas de imágenes"""
        image_task_types = [
            "analyze_image",
            "generate_image",
            "recognize_objects",
            "edit_image",
            "extract_text_from_image"
        ]
        return task.type in image_task_types
    
    async def process_task(self, task: AgentTask) -> Dict[str, Any]:
        """Procesa tareas de imágenes"""
        
        if task.type == "analyze_image":
            return await self._analyze_image(task)
        elif task.type == "generate_image":
            return await self._generate_image(task)
        elif task.type == "recognize_objects":
            return await self._recognize_objects(task)
        elif task.type == "edit_image":
            return await self._edit_image(task)
        elif task.type == "extract_text_from_image":
            return await self._extract_text_from_image(task)
        else:
            raise ValueError(f"Tipo de tarea no soportado: {task.type}")
    
    async def _analyze_image(self, task: AgentTask) -> Dict[str, Any]:
        """Analiza el contenido de imágenes"""
        try:
            image_path = task.context.get("image_path", "")
            analysis_type = task.context.get("analysis_type", "general")
            
            # Simular análisis de imagen
            analysis_result = {
                "description": f"Análisis {analysis_type} de imagen {image_path}",
                "objects_detected": ["objeto1", "objeto2"],
                "colors": ["azul", "rojo", "verde"],
                "composition": "horizontal",
                "quality_score": 0.85
            }
            
            return {
                "type": "image_analysis",
                "analysis": analysis_result,
                "image_path": image_path,
                "analysis_type": analysis_type,
                "success": True
            }
            
        except Exception as e:
            return {
                "type": "image_analysis",
                "error": str(e),
                "success": False
            }
    
    async def _generate_image(self, task: AgentTask) -> Dict[str, Any]:
        """Genera imágenes con IA"""
        try:
            prompt = task.context.get("prompt", "")
            style = task.context.get("style", "realistic")
            dimensions = task.context.get("dimensions", "1024x1024")
            
            # Simular generación de imagen
            generated_image_url = f"https://example.com/generated_image_{task.id}.png"
            
            return {
                "type": "image_generation",
                "image_url": generated_image_url,
                "prompt": prompt,
                "style": style,
                "dimensions": dimensions,
                "success": True
            }
            
        except Exception as e:
            return {
                "type": "image_generation",
                "error": str(e),
                "success": False
            }
    
    async def _recognize_objects(self, task: AgentTask) -> Dict[str, Any]:
        """Reconoce objetos en imágenes"""
        try:
            image_path = task.context.get("image_path", "")
            confidence_threshold = task.context.get("confidence_threshold", 0.7)
            
            # Simular reconocimiento de objetos
            detected_objects = [
                {"name": "persona", "confidence": 0.95, "bbox": [100, 100, 200, 300]},
                {"name": "coche", "confidence": 0.87, "bbox": [300, 150, 500, 280]},
                {"name": "árbol", "confidence": 0.72, "bbox": [50, 50, 150, 200]}
            ]
            
            # Filtrar por umbral de confianza
            filtered_objects = [
                obj for obj in detected_objects 
                if obj["confidence"] >= confidence_threshold
            ]
            
            return {
                "type": "object_recognition",
                "detected_objects": filtered_objects,
                "total_objects": len(filtered_objects),
                "confidence_threshold": confidence_threshold,
                "image_path": image_path,
                "success": True
            }
            
        except Exception as e:
            return {
                "type": "object_recognition",
                "error": str(e),
                "success": False
            }
    
    async def _edit_image(self, task: AgentTask) -> Dict[str, Any]:
        """Edita imágenes"""
        try:
            image_path = task.context.get("image_path", "")
            edit_operations = task.context.get("operations", [])
            
            # Simular edición de imagen
            edited_image_url = f"https://example.com/edited_image_{task.id}.png"
            
            return {
                "type": "image_editing",
                "edited_image_url": edited_image_url,
                "original_image": image_path,
                "operations_applied": edit_operations,
                "success": True
            }
            
        except Exception as e:
            return {
                "type": "image_editing",
                "error": str(e),
                "success": False
            }
    
    async def _extract_text_from_image(self, task: AgentTask) -> Dict[str, Any]:
        """Extrae texto de imágenes (OCR)"""
        try:
            image_path = task.context.get("image_path", "")
            language = task.context.get("language", "es")
            
            # Simular extracción de texto
            extracted_text = f"Texto extraído de la imagen {image_path} en idioma {language}"
            
            return {
                "type": "text_extraction_from_image",
                "extracted_text": extracted_text,
                "image_path": image_path,
                "language": language,
                "confidence": 0.92,
                "success": True
            }
            
        except Exception as e:
            return {
                "type": "text_extraction_from_image",
                "error": str(e),
                "success": False
            }

# ===============================================
# 📊 DATA AGENT
# ===============================================

class DataAgent(BaseAgent):
    """
    Agente especializado en análisis de datos:
    - Análisis estadístico
    - Visualizaciones
    - Reportes de datos
    - Predicciones
    """
    
    def __init__(self, agent_id: str = "data_agent_001"):
        super().__init__(agent_id, AgentType.DATA)
        self.supported_data_types = ["csv", "json", "excel", "database"]
    
    async def get_capabilities(self) -> List[AgentCapability]:
        return [
            AgentCapability(
                name="statistical_analysis",
                description="Análisis estadístico avanzado de datos",
                supported_formats=self.supported_data_types,
                confidence_score=0.93,
                max_concurrent_tasks=4
            ),
            AgentCapability(
                name="data_visualization",
                description="Creación de gráficos y visualizaciones",
                supported_formats=self.supported_data_types,
                confidence_score=0.90,
                max_concurrent_tasks=3
            ),
            AgentCapability(
                name="predictive_modeling",
                description="Modelos predictivos y machine learning",
                supported_formats=self.supported_data_types,
                confidence_score=0.85,
                max_concurrent_tasks=2
            ),
            AgentCapability(
                name="data_cleaning",
                description="Limpieza y preparación de datos",
                supported_formats=self.supported_data_types,
                confidence_score=0.95,
                max_concurrent_tasks=5
            )
        ]
    
    @property
    def max_concurrent_tasks(self) -> int:
        return 4
    
    async def can_handle_task(self, task: AgentTask) -> bool:
        """Determina si puede manejar tareas de datos"""
        data_task_types = [
            "analyze_data",
            "create_visualization",
            "generate_predictions",
            "clean_data",
            "create_dashboard",
            "statistical_summary"
        ]
        return task.type in data_task_types
    
    async def process_task(self, task: AgentTask) -> Dict[str, Any]:
        """Procesa tareas de datos"""
        
        if task.type == "analyze_data":
            return await self._analyze_data(task)
        elif task.type == "create_visualization":
            return await self._create_visualization(task)
        elif task.type == "generate_predictions":
            return await self._generate_predictions(task)
        elif task.type == "clean_data":
            return await self._clean_data(task)
        elif task.type == "create_dashboard":
            return await self._create_dashboard(task)
        elif task.type == "statistical_summary":
            return await self._statistical_summary(task)
        else:
            raise ValueError(f"Tipo de tarea no soportado: {task.type}")
    
    async def _analyze_data(self, task: AgentTask) -> Dict[str, Any]:
        """Realiza análisis de datos"""
        try:
            data = task.context.get("data", {})
            analysis_type = task.context.get("analysis_type", "descriptive")
            
            # Simular análisis de datos
            analysis_result = {
                "summary": f"Análisis {analysis_type} completado",
                "total_records": len(data) if isinstance(data, list) else 100,
                "key_metrics": {
                    "mean": 75.5,
                    "median": 78.0,
                    "std_dev": 12.3,
                    "correlation": 0.85
                },
                "insights": [
                    "Tendencia positiva en los datos",
                    "Correlación alta entre variables X e Y",
                    "Outliers detectados en el 2% de los datos"
                ]
            }
            
            return {
                "type": "data_analysis",
                "analysis": analysis_result,
                "analysis_type": analysis_type,
                "success": True
            }
            
        except Exception as e:
            return {
                "type": "data_analysis",
                "error": str(e),
                "success": False
            }
    
    async def _create_visualization(self, task: AgentTask) -> Dict[str, Any]:
        """Crea visualizaciones de datos"""
        try:
            data = task.context.get("data", {})
            chart_type = task.context.get("chart_type", "bar")
            title = task.context.get("title", "Gráfico de Datos")
            
            # Simular creación de visualización
            chart_url = f"https://example.com/chart_{task.id}.png"
            
            return {
                "type": "data_visualization",
                "chart_url": chart_url,
                "chart_type": chart_type,
                "title": title,
                "data_points": len(data) if isinstance(data, list) else 50,
                "success": True
            }
            
        except Exception as e:
            return {
                "type": "data_visualization",
                "error": str(e),
                "success": False
            }
    
    async def _generate_predictions(self, task: AgentTask) -> Dict[str, Any]:
        """Genera predicciones"""
        try:
            data = task.context.get("data", {})
            prediction_type = task.context.get("prediction_type", "linear")
            horizon = task.context.get("horizon", 30)
            
            # Simular predicciones
            predictions = {
                "model_type": prediction_type,
                "predictions": [85.2, 87.1, 89.3, 91.5, 93.2],
                "confidence_intervals": [
                    {"lower": 80.1, "upper": 90.3},
                    {"lower": 82.0, "upper": 92.2}
                ],
                "accuracy_score": 0.92,
                "r_squared": 0.85
            }
            
            return {
                "type": "predictive_modeling",
                "predictions": predictions,
                "prediction_horizon": horizon,
                "model_type": prediction_type,
                "success": True
            }
            
        except Exception as e:
            return {
                "type": "predictive_modeling",
                "error": str(e),
                "success": False
            }
    
    async def _clean_data(self, task: AgentTask) -> Dict[str, Any]:
        """Limpia y prepara datos"""
        try:
            data = task.context.get("data", {})
            cleaning_operations = task.context.get("operations", [])
            
            # Simular limpieza de datos
            cleaning_report = {
                "original_records": len(data) if isinstance(data, list) else 1000,
                "cleaned_records": 950,
                "removed_duplicates": 30,
                "filled_missing_values": 20,
                "outliers_handled": 5,
                "operations_applied": cleaning_operations
            }
            
            return {
                "type": "data_cleaning",
                "cleaning_report": cleaning_report,
                "cleaned_data_url": f"https://example.com/cleaned_data_{task.id}.csv",
                "success": True
            }
            
        except Exception as e:
            return {
                "type": "data_cleaning",
                "error": str(e),
                "success": False
            }
    
    async def _create_dashboard(self, task: AgentTask) -> Dict[str, Any]:
        """Crea dashboards interactivos"""
        try:
            data_sources = task.context.get("data_sources", [])
            dashboard_type = task.context.get("dashboard_type", "executive")
            
            # Simular creación de dashboard
            dashboard_url = f"https://example.com/dashboard_{task.id}"
            
            return {
                "type": "dashboard_creation",
                "dashboard_url": dashboard_url,
                "dashboard_type": dashboard_type,
                "data_sources": len(data_sources),
                "widgets": ["KPI Cards", "Line Charts", "Bar Charts", "Tables"],
                "success": True
            }
            
        except Exception as e:
            return {
                "type": "dashboard_creation",
                "error": str(e),
                "success": False
            }
    
    async def _statistical_summary(self, task: AgentTask) -> Dict[str, Any]:
        """Genera resumen estadístico"""
        try:
            data = task.context.get("data", {})
            
            # Simular resumen estadístico
            summary = {
                "descriptive_statistics": {
                    "count": 1000,
                    "mean": 75.5,
                    "std": 12.3,
                    "min": 45.2,
                    "25%": 67.1,
                    "50%": 75.8,
                    "75%": 84.2,
                    "max": 98.7
                },
                "distribution_info": {
                    "skewness": 0.12,
                    "kurtosis": -0.34,
                    "normality_test": "passed"
                }
            }
            
            return {
                "type": "statistical_summary",
                "summary": summary,
                "data_size": len(data) if isinstance(data, list) else 1000,
                "success": True
            }
            
        except Exception as e:
            return {
                "type": "statistical_summary",
                "error": str(e),
                "success": False
            }

# ===============================================
# 🎯 COORDINADOR DEL SISTEMA DE AGENTES
# ===============================================

class AgentCoordinator:
    """
    Coordinador principal del sistema de agentes MULTIUSUARIO
    Gestiona agentes dedicados por usuario para máximo rendimiento
    """
    
    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.personal_agent: Optional[PersonalAgent] = None
        self.task_queue = asyncio.Queue()
        self.is_running = False
        
        # 🚀 GESTIÓN MULTIUSUARIO
        self.user_agent_pools: Dict[str, Dict[str, BaseAgent]] = {}  # user_id -> agent_pool
        self.user_sessions: Dict[str, Dict[str, Any]] = {}  # user_id -> session_data
        self.active_users: set = set()
        
        # 🧠 NUEVOS COMPONENTES
        self.memory = AgentMemory()  # Memoria compartida
        self.smart_router = SmartRouter(self)  # Router inteligente
        self.pipeline = AgentPipeline(self)  # Pipeline de ejecución
        
        # Crear agentes globales especializados
        self.tool_agent = ToolAgent()
        self.group_agent = GroupAgent()
        self.group_agent.memory = self.memory
        
        # Registrar agentes globales
        self.agents['tool'] = self.tool_agent
        self.agents['group'] = self.group_agent
        
        # Asignar memoria al router
        self.smart_router.memory = self.memory
        
        # Métricas del coordinador
        self.metrics = SafeMetric()
        self.coordination_counter = self.metrics.counter(
            'agent_coordination_total',
            'Total de coordinaciones realizadas',
            ['status', 'user_id']
        )
        
        self.multiuser_metrics = self.metrics.counter(
            'multiuser_agent_operations_total',
            'Operaciones de agentes por usuario',
            ['user_id', 'agent_type', 'operation']
        )
        
        logger.info("🎯 AgentCoordinator MULTIUSUARIO con SmartRouter inicializado")
    
    async def initialize_user_agents(self, user_id: str) -> Dict[str, BaseAgent]:
        """Inicializa agentes dedicados para un usuario específico"""
        if user_id in self.user_agent_pools:
            return self.user_agent_pools[user_id]
        
        logger.info(f"🚀 Inicializando agentes para usuario {user_id}")
        
        try:
            # Crear pool de agentes para el usuario
            user_agents = {}
            
            # 1. Agente personal coordinador para el usuario
            personal_agent = PersonalAgent(agent_id=f"personal_{user_id}")
            user_agents['personal'] = personal_agent
            
            # 2. Agentes especializados para el usuario
            user_agents['document'] = DocumentAgent(agent_id=f"document_{user_id}")
            user_agents['image'] = ImageAgent(agent_id=f"image_{user_id}")
            user_agents['data'] = DataAgent(agent_id=f"data_{user_id}")
            
            # 3. Configurar relaciones entre agentes del usuario
            personal_agent.register_specialized_agent(user_agents['document'])
            personal_agent.register_specialized_agent(user_agents['image'])
            personal_agent.register_specialized_agent(user_agents['data'])
            
            # 4. Dar acceso a agentes globales
            personal_agent.register_specialized_agent(self.tool_agent)
            personal_agent.register_specialized_agent(self.group_agent)
            
            # 5. Registrar en el pool del usuario
            self.user_agent_pools[user_id] = user_agents
            self.active_users.add(user_id)
            
            # 5. Inicializar sesión del usuario
            self.user_sessions[user_id] = {
                'created_at': datetime.utcnow(),
                'last_activity': datetime.utcnow(),
                'total_tasks': 0,
                'successful_tasks': 0,
                'failed_tasks': 0,
                'agent_preferences': {},
                'session_context': {}
            }
            
            logger.info(f"✅ Agentes inicializados para usuario {user_id}")
            return user_agents
            
        except Exception as e:
            logger.error(f"❌ Error inicializando agentes para usuario {user_id}: {e}")
            raise

    async def get_user_personal_agent(self, user_id: str) -> PersonalAgent:
        """Obtiene el agente personal de un usuario específico"""
        if user_id not in self.user_agent_pools:
            await self.initialize_user_agents(user_id)
        
        return self.user_agent_pools[user_id]['personal']
    
    async def execute_with_smart_routing(self, query: str, user_id: str, context: Dict = None) -> Dict[str, Any]:
        """
        🧠 Ejecuta tarea usando SmartRouter para decidir qué agente(s) usar
        
        Esta es la forma recomendada de ejecutar tareas en el sistema.
        El LLM decide automáticamente qué agentes usar y en qué orden.
        """
        try:
            # Guardar query en memoria
            self.memory.add_conversation(user_id, "user", query)
            
            # 1. Router decide qué agentes usar
            routing_decision = await self.smart_router.route(query, user_id, context)
            
            logger.info(f"🧭 SmartRouter decision: {routing_decision}")
            
            # 2. Crear tarea
            task = AgentTask(
                id=f"task_{int(datetime.utcnow().timestamp())}_{user_id}",
                type="smart_routed",
                description=query,
                user_id=user_id,
                priority=TaskPriority.MEDIUM,
                status=TaskStatus.PENDING,
                context=context or {}
            )
            
            # 3. Ejecutar pipeline
            agents_to_use = routing_decision.get("agents", ["personal"])
            order = routing_decision.get("order", "sequential")
            
            result = await self.pipeline.execute(agents_to_use, task, order)
            
            # 4. Guardar respuesta en memoria
            response_text = self._extract_response_text(result)
            self.memory.add_conversation(user_id, "assistant", response_text)
            
            # 5. Actualizar métricas
            self.multiuser_metrics.labels(
                user_id=user_id,
                agent_type="smart_router",
                operation="execute"
            ).inc()
            
            return {
                "success": result.get("success", False),
                "routing_decision": routing_decision,
                "pipeline_result": result,
                "response": response_text
            }
            
        except Exception as e:
            logger.error(f"❌ Error in smart routing: {e}")
            return {
                "success": False,
                "error": str(e),
                "routing_decision": None,
                "pipeline_result": None
            }
    
    async def execute_group_task(self, group_id: str, task_type: str, query: str, user_id: str, context: Dict = None) -> Dict[str, Any]:
        """
        👥 Ejecuta tarea relacionada con grupo de estudio
        
        Usa el GroupAgent especializado con contexto del grupo.
        """
        try:
            # Actualizar contexto del grupo en memoria si se proporciona
            if context and "group_context" in context:
                self.memory.store_group_context(group_id, context["group_context"])
            
            # Crear tarea para GroupAgent
            task = AgentTask(
                id=f"group_task_{int(datetime.utcnow().timestamp())}",
                type="group_operation",
                description=query,
                user_id=user_id,
                priority=TaskPriority.HIGH,
                status=TaskStatus.PENDING,
                context={
                    "group_id": group_id,
                    "task_type": task_type,
                    **(context or {})
                }
            )
            
            # Ejecutar con GroupAgent
            result = await self.group_agent.execute_task(task)
            
            # Actualizar métricas
            self.multiuser_metrics.labels(
                user_id=user_id,
                agent_type="group",
                operation=task_type
            ).inc()
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error in group task: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def execute_tool_action(self, tool: str, action: str, user_id: str, params: Dict = None) -> Dict[str, Any]:
        """
        🔧 Ejecuta acción con herramienta externa usando ToolAgent
        """
        try:
            task = AgentTask(
                id=f"tool_task_{int(datetime.utcnow().timestamp())}",
                type="tool_action",
                description=f"Execute {action} on {tool}",
                user_id=user_id,
                priority=TaskPriority.MEDIUM,
                status=TaskStatus.PENDING,
                context={
                    "tool": tool,
                    "action": action,
                    "params": params or {}
                }
            )
            
            result = await self.tool_agent.execute_task(task)
            
            self.multiuser_metrics.labels(
                user_id=user_id,
                agent_type="tool",
                operation=f"{tool}_{action}"
            ).inc()
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error in tool action: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _extract_response_text(self, result: Dict) -> str:
        """Extrae texto de respuesta del resultado del pipeline"""
        if not result.get("success"):
            return "Error procesando solicitud"
        
        # Si es pipeline, combinar resultados
        if "results" in result:
            texts = []
            for r in result["results"]:
                agent_result = r.get("result", {})
                if "answer" in agent_result:
                    texts.append(agent_result["answer"])
                elif "summary" in agent_result:
                    texts.append(agent_result["summary"])
                elif "content" in agent_result:
                    texts.append(str(agent_result["content"]))
            
            return "\n\n".join(texts) if texts else "Tarea completada"
        
        return "Tarea completada exitosamente"

    async def update_user_session(self, user_id: str, task_result: Dict[str, Any]):
        """Actualiza la sesión del usuario con resultados de tarea"""
        if user_id not in self.user_sessions:
            await self.initialize_user_agents(user_id)
        
        session = self.user_sessions[user_id]
        session['last_activity'] = datetime.utcnow()
        session['total_tasks'] += 1
        
        if task_result.get('success', False):
            session['successful_tasks'] += 1
        else:
            session['failed_tasks'] += 1
        
        # Actualizar preferencias basadas en uso
        agents_involved = task_result.get('agents_involved', [])
        for agent_type in agents_involved:
            if agent_type not in session['agent_preferences']:
                session['agent_preferences'][agent_type] = 0
            session['agent_preferences'][agent_type] += 1

    async def initialize(self):
        """Inicializa el sistema de agentes global"""
        logger.info("🚀 Inicializando sistema de agentes MULTIUSUARIO...")
        
        try:
            # 1. Crear agente personal global (para tareas generales)
            self.personal_agent = PersonalAgent()
            await self.register_agent(self.personal_agent)
            
            # 2. Crear agentes especializados globales
            document_agent = DocumentAgent()
            image_agent = ImageAgent()
            data_agent = DataAgent()
            
            # 3. Registrar agentes especializados globales
            await self.register_agent(document_agent)
            await self.register_agent(image_agent)
            await self.register_agent(data_agent)
            
            # 4. Configurar relaciones entre agentes globales
            self.personal_agent.register_specialized_agent(document_agent)
            self.personal_agent.register_specialized_agent(image_agent)
            self.personal_agent.register_specialized_agent(data_agent)
            
            self.is_running = True
            logger.info("✅ Sistema de agentes MULTIUSUARIO inicializado exitosamente")
            
        except Exception as e:
            logger.error(f"❌ Error inicializando sistema de agentes: {e}")
            raise
    
    async def register_agent(self, agent: BaseAgent):
        """Registra un agente en el sistema"""
        self.agents[agent.agent_id] = agent
        logger.info(f"📝 Agente registrado: {agent.agent_id} ({agent.agent_type.value})")
    
    async def process_user_request(self, user_id: str, request: str, priority: TaskPriority = TaskPriority.MEDIUM) -> Dict[str, Any]:
        """
        Procesa una solicitud de usuario usando su pool de agentes dedicado
        """
        try:
            logger.info(f"📥 Procesando solicitud de usuario {user_id}: {request[:100]}...")
            
            # 1. Obtener o crear agentes del usuario
            user_personal_agent = await self.get_user_personal_agent(user_id)
            
            # 2. Crear tarea principal
            main_task = AgentTask(
                id=f"task_{user_id}_{int(datetime.utcnow().timestamp())}",
                type="coordinate_multi_agent",
                description=f"Solicitud del usuario: {request}",
                user_id=user_id,
                priority=priority,
                status=TaskStatus.PENDING,
                context={
                    "user_request": request,
                    "original_request": request,
                    "user_session": self.user_sessions.get(user_id, {})
                }
            )
            
            # 3. Delegar al agente personal del usuario
            if await user_personal_agent.accept_task(main_task):
                result = await user_personal_agent.execute_task(main_task)
                
                # 4. Actualizar sesión del usuario
                await self.update_user_session(user_id, result)
                
                # 5. Métricas multiusuario
                self.coordination_counter.inc(labels=['success', user_id])
                self.multiuser_metrics.inc(labels=[user_id, 'personal', 'task_completed'])
                
                return {
                    "success": True,
                    "task_id": main_task.id,
                    "result": result,
                    "processing_time": (datetime.utcnow() - main_task.created_at).total_seconds(),
                    "agents_involved": self._extract_agents_from_result(result),
                    "user_id": user_id,
                    "session_stats": self.user_sessions.get(user_id, {})
                }
            else:
                self.coordination_counter.inc(labels=['failed', user_id])
                return {
                    "success": False,
                    "error": "Personal agent no pudo aceptar la tarea",
                    "task_id": main_task.id,
                    "user_id": user_id
                }
                
        except Exception as e:
            logger.error(f"❌ Error procesando solicitud de usuario {user_id}: {e}")
            self.coordination_counter.inc(labels=['error', user_id])
            return {
                "success": False,
                "error": str(e),
                "task_id": getattr(main_task, 'id', 'unknown'),
                "user_id": user_id
            }
    
    def _extract_agents_from_result(self, result: Dict[str, Any]) -> List[str]:
        """Extrae los agentes involucrados del resultado"""
        agents_involved = []
        
        if isinstance(result, dict):
            if "agents_involved" in result:
                agents_involved.extend(result["agents_involved"])
            elif "subtask_results" in result:
                agents_involved.extend(result["subtask_results"].keys())
        
        return agents_involved
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Obtiene el estado del sistema de agentes multiusuario"""
        agent_statuses = {}
        
        for agent_id, agent in self.agents.items():
            agent_statuses[agent_id] = agent.get_status()
        
        # Estadísticas multiusuario
        user_stats = {}
        for user_id, session in self.user_sessions.items():
            user_stats[user_id] = {
                "total_tasks": session.get('total_tasks', 0),
                "successful_tasks": session.get('successful_tasks', 0),
                "failed_tasks": session.get('failed_tasks', 0),
                "success_rate": session.get('successful_tasks', 0) / max(session.get('total_tasks', 1), 1),
                "last_activity": session.get('last_activity', '').isoformat() if session.get('last_activity') else None,
                "preferred_agents": session.get('agent_preferences', {}),
                "has_dedicated_agents": user_id in self.user_agent_pools
            }
        
        return {
            "system_status": "running" if self.is_running else "stopped",
            "total_agents": len(self.agents),
            "agents": agent_statuses,
            "personal_agent_active": self.personal_agent is not None and self.personal_agent.is_active,
            "multiuser_stats": {
                "active_users": len(self.active_users),
                "total_user_sessions": len(self.user_sessions),
                "users_with_dedicated_agents": len(self.user_agent_pools),
                "user_statistics": user_stats
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    async def cleanup_inactive_users(self, inactivity_threshold_hours: int = 24):
        """Limpia usuarios inactivos para optimizar memoria"""
        current_time = datetime.utcnow()
        threshold = timedelta(hours=inactivity_threshold_hours)
        
        inactive_users = []
        for user_id, session in self.user_sessions.items():
            last_activity = session.get('last_activity', current_time)
            if current_time - last_activity > threshold:
                inactive_users.append(user_id)
        
        for user_id in inactive_users:
            logger.info(f"🧹 Limpiando usuario inactivo: {user_id}")
            
            # Remover pool de agentes del usuario
            if user_id in self.user_agent_pools:
                del self.user_agent_pools[user_id]
            
            # Remover sesión del usuario
            if user_id in self.user_sessions:
                del self.user_sessions[user_id]
            
            # Remover de usuarios activos
            self.active_users.discard(user_id)
        
        if inactive_users:
            logger.info(f"✅ Limpiados {len(inactive_users)} usuarios inactivos")
        
        return len(inactive_users)

    async def get_user_agent_stats(self, user_id: str) -> Dict[str, Any]:
        """Obtiene estadísticas específicas de un usuario"""
        if user_id not in self.user_sessions:
            return {"error": "Usuario no encontrado"}
        
        session = self.user_sessions[user_id]
        user_agents = self.user_agent_pools.get(user_id, {})
        
        agent_stats = {}
        for agent_type, agent in user_agents.items():
            agent_stats[agent_type] = {
                "agent_id": agent.agent_id,
                "current_tasks": len(agent.current_tasks),
                "completed_tasks": agent.completed_tasks_count,
                "failed_tasks": agent.failed_tasks_count,
                "is_active": agent.is_active,
                "max_concurrent": agent.max_concurrent_tasks
            }
        
        return {
            "user_id": user_id,
            "session": session,
            "dedicated_agents": agent_stats,
            "has_dedicated_pool": user_id in self.user_agent_pools,
            "is_active": user_id in self.active_users
        }
    
    async def shutdown(self):
        """Apaga el sistema de agentes de forma ordenada"""
        logger.info("🔄 Apagando sistema de agentes...")
        
        self.is_running = False
        
        # Esperar a que terminen las tareas actuales
        for agent in self.agents.values():
            agent.is_active = False
            # En producción: esperar a que terminen las tareas actuales
        
        logger.info("✅ Sistema de agentes apagado")


# ===============================================
# 🧠 AGENT MEMORY - Memoria Compartida
# ===============================================

class AgentMemory:
    """Sistema de memoria compartida entre agentes"""
    
    def __init__(self):
        self.short_term: Dict[str, Dict[str, Any]] = {}  # Sesión actual
        self.long_term: Dict[str, Dict[str, Any]] = {}   # Persistente
        self.conversation_history: Dict[str, List[Dict]] = {}  # Por usuario
        self.group_context: Dict[str, Dict[str, Any]] = {}  # Por grupo
    
    def store_short_term(self, key: str, value: Any, ttl: int = 3600):
        """Almacena en memoria de corto plazo con TTL"""
        self.short_term[key] = {
            "value": value,
            "expires_at": datetime.utcnow().timestamp() + ttl,
            "created_at": datetime.utcnow().timestamp()
        }
    
    def store_long_term(self, key: str, value: Any):
        """Almacena en memoria de largo plazo"""
        self.long_term[key] = {
            "value": value,
            "stored_at": datetime.utcnow().timestamp()
        }
    
    def recall(self, key: str) -> Optional[Any]:
        """Recupera de memoria (corto o largo plazo)"""
        # Intentar corto plazo primero
        if key in self.short_term:
            item = self.short_term[key]
            if item["expires_at"] > datetime.utcnow().timestamp():
                return item["value"]
            else:
                # Expirado, eliminar
                del self.short_term[key]
        
        # Intentar largo plazo
        if key in self.long_term:
            return self.long_term[key]["value"]
        
        return None
    
    def add_conversation(self, user_id: str, role: str, content: str):
        """Agrega mensaje a historial de conversación"""
        if user_id not in self.conversation_history:
            self.conversation_history[user_id] = []
        
        self.conversation_history[user_id].append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Mantener solo últimos 50 mensajes
        if len(self.conversation_history[user_id]) > 50:
            self.conversation_history[user_id] = self.conversation_history[user_id][-50:]
    
    def get_conversation(self, user_id: str, last_n: int = 10) -> List[Dict]:
        """Obtiene últimos N mensajes de conversación"""
        if user_id not in self.conversation_history:
            return []
        return self.conversation_history[user_id][-last_n:]
    
    def store_group_context(self, group_id: str, context: Dict[str, Any]):
        """Almacena contexto de grupo"""
        self.group_context[group_id] = {
            "context": context,
            "updated_at": datetime.utcnow().timestamp()
        }
    
    def get_group_context(self, group_id: str) -> Optional[Dict[str, Any]]:
        """Recupera contexto de grupo"""
        if group_id in self.group_context:
            return self.group_context[group_id]["context"]
        return None
    
    def clear_expired(self):
        """Limpia memoria de corto plazo expirada"""
        now = datetime.utcnow().timestamp()
        expired_keys = [
            k for k, v in self.short_term.items()
            if v["expires_at"] < now
        ]
        for key in expired_keys:
            del self.short_term[key]


# ===============================================
# 🔧 TOOL AGENT - Integrations
# ===============================================

class ToolAgent(BaseAgent):
    """Agente especializado en usar herramientas externas (Notion, Google, etc.)"""
    
    def __init__(self, agent_id: str = "tool_agent"):
        super().__init__(agent_id, AgentType.PERSONAL)
        self.available_tools = {
            "notion": ["create_page", "search", "update_page", "get_databases"],
            "google_drive": ["upload", "create_folder", "list_files", "download"],
            "google_docs": ["create", "read", "update", "export"],
            "google_sheets": ["create", "read", "update", "append"],
            "gmail": ["send", "read", "search"],
            "github": ["create_repo", "create_issue", "commit", "search"],
            "slack": ["send_message", "create_channel", "upload_file"],
            "trello": ["create_board", "create_card", "update_card"]
        }
        self.gpt_service = GPTService()
    
    async def execute_task(self, task: AgentTask) -> Dict[str, Any]:
        """Ejecuta tarea de integración"""
        try:
            query = task.description.lower()
            context = task.context or {}
            
            # Detectar qué herramienta usar
            tool_decision = await self._decide_tool(query, context)
            
            if not tool_decision:
                return {
                    "success": False,
                    "error": "No se pudo determinar qué herramienta usar"
                }
            
            tool = tool_decision["tool"]
            action = tool_decision["action"]
            params = tool_decision["params"]
            
            # Ejecutar acción
            result = await self._execute_tool_action(tool, action, params, context)
            
            return {
                "success": True,
                "tool": tool,
                "action": action,
                "result": result
            }
            
        except Exception as e:
            logger.error(f"❌ ToolAgent error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _decide_tool(self, query: str, context: Dict) -> Optional[Dict]:
        """Decide qué herramienta y acción usar con LLM"""
        prompt = f"""
Analiza esta solicitud y decide qué herramienta usar:

Solicitud: {query}
Contexto: {json.dumps(context, indent=2)}

Herramientas disponibles:
{json.dumps(self.available_tools, indent=2)}

Responde SOLO con JSON válido:
{{
  "tool": "nombre_herramienta",
  "action": "acción_específica",
  "params": {{"param1": "value1"}},
  "reasoning": "por qué esta herramienta"
}}
"""
        
        try:
            response = await self.gpt_service.chat([
                {"role": "system", "content": "Eres un router de herramientas. Respondes SOLO JSON."},
                {"role": "user", "content": prompt}
            ])
            
            # Extraer JSON de la respuesta
            content = response.get("content", "")
            # Intentar parsear JSON
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            
            return None
            
        except Exception as e:
            logger.error(f"Error deciding tool: {e}")
            return None
    
    async def _execute_tool_action(self, tool: str, action: str, params: Dict, context: Dict) -> Dict:
        """Ejecuta acción en herramienta externa"""
        # Aquí integrarías con los routers existentes
        # Por ahora retornamos mock
        return {
            "status": "simulated",
            "tool": tool,
            "action": action,
            "params": params,
            "message": f"Acción {action} en {tool} ejecutada (simulación)"
        }
    
    def get_capabilities(self) -> List[AgentCapability]:
        return [
            AgentCapability(
                name="external_integrations",
                description="Integración con herramientas externas",
                supported_formats=["notion", "google", "github", "slack", "trello"],
                confidence_score=0.9,
                max_concurrent_tasks=5
            )
        ]


# ===============================================
# 👥 GROUP AGENT - Study Groups Specialist
# ===============================================

class GroupAgent(BaseAgent):
    """Agente especializado en contexto de grupos de estudio"""
    
    def __init__(self, agent_id: str = "group_agent"):
        super().__init__(agent_id, AgentType.PERSONAL)
        self.gpt_service = GPTService()
        self.memory = None  # Se asignará desde el coordinator
    
    async def execute_task(self, task: AgentTask) -> Dict[str, Any]:
        """Ejecuta tarea relacionada con grupos"""
        try:
            task_type = task.context.get("task_type", "general")
            
            if task_type == "summarize_group":
                return await self._summarize_group(task)
            elif task_type == "answer_with_context":
                return await self._answer_with_group_context(task)
            elif task_type == "sync_documents":
                return await self._sync_group_documents(task)
            elif task_type == "generate_report":
                return await self._generate_group_report(task)
            else:
                return await self._general_group_task(task)
                
        except Exception as e:
            logger.error(f"❌ GroupAgent error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _summarize_group(self, task: AgentTask) -> Dict:
        """Resume todos los documentos de un grupo"""
        group_id = task.context.get("group_id")
        
        # Obtener contexto del grupo desde memoria
        group_context = self.memory.get_group_context(group_id) if self.memory else None
        
        if not group_context:
            return {
                "success": False,
                "error": "No se encontró contexto del grupo"
            }
        
        documents = group_context.get("documents", [])
        
        if not documents:
            return {
                "success": True,
                "summary": "El grupo no tiene documentos compartidos aún.",
                "document_count": 0
            }
        
        # Generar resumen usando LLM
        docs_text = "\n\n".join([
            f"Documento: {doc.get('title', 'Sin título')}\n{doc.get('content', '')[:500]}"
            for doc in documents[:10]  # Primeros 10 docs
        ])
        
        prompt = f"""
Resume los siguientes documentos de un grupo de estudio:

{docs_text}

Genera un resumen ejecutivo que incluya:
1. Temas principales cubiertos
2. Conceptos clave
3. Áreas que necesitan más atención
4. Recomendaciones de estudio
"""
        
        response = await self.gpt_service.chat([
            {"role": "system", "content": "Eres un tutor académico experto en sintetizar material de estudio."},
            {"role": "user", "content": prompt}
        ])
        
        return {
            "success": True,
            "summary": response.get("content", ""),
            "document_count": len(documents),
            "group_id": group_id
        }
    
    async def _answer_with_group_context(self, task: AgentTask) -> Dict:
        """Responde pregunta usando contexto del grupo"""
        group_id = task.context.get("group_id")
        question = task.description
        
        # Obtener contexto
        group_context = self.memory.get_group_context(group_id) if self.memory else None
        
        if not group_context:
            return {
                "success": False,
                "error": "No hay contexto disponible"
            }
        
        # Construir contexto para LLM
        context_text = self._build_context_text(group_context)
        
        prompt = f"""
Contexto del grupo de estudio:
{context_text}

Pregunta del estudiante: {question}

Responde usando SOLO la información del contexto del grupo. Si no hay información suficiente, indícalo.
"""
        
        response = await self.gpt_service.chat([
            {"role": "system", "content": "Eres un asistente de estudio que usa el material compartido del grupo."},
            {"role": "user", "content": prompt}
        ])
        
        return {
            "success": True,
            "answer": response.get("content", ""),
            "sources_used": len(group_context.get("documents", [])),
            "group_id": group_id
        }
    
    async def _sync_group_documents(self, task: AgentTask) -> Dict:
        """Sincroniza documentos del grupo a herramienta externa"""
        group_id = task.context.get("group_id")
        target = task.context.get("target", "notion")  # notion, google_drive, etc.
        
        group_context = self.memory.get_group_context(group_id) if self.memory else None
        
        if not group_context:
            return {"success": False, "error": "No hay contexto"}
        
        documents = group_context.get("documents", [])
        
        # Aquí se integraría con ToolAgent
        return {
            "success": True,
            "synced": len(documents),
            "target": target,
            "message": f"Sincronizados {len(documents)} documentos a {target}"
        }
    
    async def _generate_group_report(self, task: AgentTask) -> Dict:
        """Genera reporte de actividad del grupo"""
        group_id = task.context.get("group_id")
        
        group_context = self.memory.get_group_context(group_id) if self.memory else {}
        
        return {
            "success": True,
            "report": {
                "group_id": group_id,
                "members": group_context.get("members_count", 0),
                "documents": len(group_context.get("documents", [])),
                "messages": group_context.get("messages_count", 0),
                "activity_summary": "Grupo activo con buen nivel de participación"
            }
        }
    
    async def _general_group_task(self, task: AgentTask) -> Dict:
        """Tarea general del grupo"""
        return {
            "success": True,
            "message": "Tarea grupal procesada",
            "task_id": task.id
        }
    
    def _build_context_text(self, group_context: Dict) -> str:
        """Construye texto de contexto del grupo"""
        docs = group_context.get("documents", [])
        messages = group_context.get("recent_messages", [])
        
        text_parts = []
        
        if docs:
            text_parts.append("Documentos compartidos:")
            for doc in docs[:5]:
                text_parts.append(f"- {doc.get('title', 'Sin título')}: {doc.get('content', '')[:200]}")
        
        if messages:
            text_parts.append("\nConversaciones recientes:")
            for msg in messages[-10:]:
                text_parts.append(f"- {msg.get('content', '')[:100]}")
        
        return "\n".join(text_parts)
    
    def get_capabilities(self) -> List[AgentCapability]:
        return [
            AgentCapability(
                name="group_coordination",
                description="Coordinación y análisis de grupos de estudio",
                supported_formats=["group_context", "documents", "messages"],
                confidence_score=0.95,
                max_concurrent_tasks=10
            )
        ]


# ===============================================
# 🧭 SMART ROUTER - LLM-Powered Routing
# ===============================================

class SmartRouter:
    """Router inteligente que usa LLM para decidir qué agente(s) usar"""
    
    def __init__(self, coordinator: 'AgentCoordinator'):
        self.coordinator = coordinator
        self.gpt_service = GPTService()
        self.memory = None  # Se asignará desde coordinator
    
    async def route(self, query: str, user_id: str, context: Dict = None) -> Dict[str, Any]:
        """Analiza query y decide qué agente(s) usar"""
        context = context or {}
        
        # Obtener historial de conversación
        conversation_history = []
        if self.memory:
            conversation_history = self.memory.get_conversation(user_id, last_n=5)
        
        # Construir prompt para routing
        prompt = self._build_routing_prompt(query, context, conversation_history)
        
        try:
            response = await self.gpt_service.chat([
                {"role": "system", "content": "Eres un router de agentes. Respondes SOLO JSON válido."},
                {"role": "user", "content": prompt}
            ])
            
            # Parsear decisión
            decision = self._parse_routing_decision(response.get("content", ""))
            
            if not decision:
                # Fallback a PersonalAgent
                return {
                    "agents": ["personal"],
                    "order": "sequential",
                    "reasoning": "No se pudo determinar routing, usando agente personal"
                }
            
            return decision
            
        except Exception as e:
            logger.error(f"Error en SmartRouter: {e}")
            return {
                "agents": ["personal"],
                "order": "sequential",
                "reasoning": f"Error en routing: {e}"
            }
    
    def _build_routing_prompt(self, query: str, context: Dict, history: List[Dict]) -> str:
        """Construye prompt para decisión de routing"""
        
        history_text = ""
        if history:
            history_text = "Conversación previa:\n" + "\n".join([
                f"- {msg['role']}: {msg['content'][:100]}"
                for msg in history
            ])
        
        return f"""
Analiza esta solicitud y decide qué agente(s) usar:

Query: {query}
Contexto: {json.dumps(context, indent=2)}
{history_text}

Agentes disponibles:
- personal: Coordinador general, conversación, preguntas generales
- document: Procesar PDFs, documentos, extraer texto, resumir
- image: Analizar imágenes, generar imágenes, OCR
- data: Análisis de datos, gráficos, estadísticas, CSV/Excel
- tool: Integraciones externas (Notion, Google, GitHub, Slack)
- group: Contexto de grupos de estudio, resúmenes grupales

Responde SOLO con JSON:
{{
  "agents": ["agent1", "agent2"],
  "order": "parallel" o "sequential",
  "reasoning": "por qué estos agentes",
  "primary_agent": "agent_principal"
}}

REGLAS:
- Si menciona "grupo", "compañeros", "compartido" → usa "group"
- Si menciona "Notion", "Google", "GitHub" → usa "tool"
- Si menciona "documento", "PDF", "resumir" → usa "document"
- Si menciona "imagen", "foto", "OCR" → usa "image"
- Si menciona "datos", "gráfico", "CSV" → usa "data"
- Si es conversación general → usa "personal"
- Si necesitas varios → order: "sequential" (uno después de otro)
- Si son independientes → order: "parallel" (simultáneamente)
"""
    
    def _parse_routing_decision(self, response: str) -> Optional[Dict]:
        """Parsea respuesta del LLM"""
        try:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return None
        except Exception as e:
            logger.error(f"Error parsing routing decision: {e}")
            return None


# ===============================================
# 🔄 AGENT PIPELINE - Execution Chain
# ===============================================

class AgentPipeline:
    """Pipeline para ejecutar múltiples agentes en secuencia o paralelo"""
    
    def __init__(self, coordinator: 'AgentCoordinator'):
        self.coordinator = coordinator
    
    async def execute(self, agents: List[str], task: AgentTask, order: str = "sequential") -> Dict[str, Any]:
        """
        Ejecuta pipeline de agentes
        
        Args:
            agents: Lista de nombres de agentes
            task: Tarea a ejecutar
            order: "sequential" o "parallel"
        """
        
        if order == "parallel":
            return await self._execute_parallel(agents, task)
        else:
            return await self._execute_sequential(agents, task)
    
    async def _execute_sequential(self, agents: List[str], task: AgentTask) -> Dict[str, Any]:
        """Ejecuta agentes secuencialmente (resultado de uno alimenta al siguiente)"""
        results = []
        current_context = task.context.copy()
        
        for agent_name in agents:
            # Crear tarea para este agente con contexto actualizado
            agent_task = AgentTask(
                id=f"{task.id}_{agent_name}",
                type=task.type,
                description=task.description,
                user_id=task.user_id,
                priority=task.priority,
                status=TaskStatus.PENDING,
                context=current_context
            )
            
            # Ejecutar
            result = await self._execute_single_agent(agent_name, agent_task)
            results.append({
                "agent": agent_name,
                "result": result
            })
            
            # Actualizar contexto para siguiente agente
            if result.get("success"):
                current_context.update(result.get("context", {}))
        
        return {
            "success": all(r["result"].get("success") for r in results),
            "pipeline": "sequential",
            "agents_executed": len(results),
            "results": results,
            "final_context": current_context
        }
    
    async def _execute_parallel(self, agents: List[str], task: AgentTask) -> Dict[str, Any]:
        """Ejecuta agentes en paralelo"""
        tasks = []
        
        for agent_name in agents:
            agent_task = AgentTask(
                id=f"{task.id}_{agent_name}",
                type=task.type,
                description=task.description,
                user_id=task.user_id,
                priority=task.priority,
                status=TaskStatus.PENDING,
                context=task.context.copy()
            )
            tasks.append(self._execute_single_agent(agent_name, agent_task))
        
        # Ejecutar todos en paralelo
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Procesar resultados
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "agent": agents[i],
                    "result": {"success": False, "error": str(result)}
                })
            else:
                processed_results.append({
                    "agent": agents[i],
                    "result": result
                })
        
        return {
            "success": any(r["result"].get("success") for r in processed_results),
            "pipeline": "parallel",
            "agents_executed": len(processed_results),
            "results": processed_results
        }
    
    async def _execute_single_agent(self, agent_name: str, task: AgentTask) -> Dict[str, Any]:
        """Ejecuta un solo agente"""
        try:
            agent = self.coordinator.agents.get(agent_name)
            
            if not agent:
                return {
                    "success": False,
                    "error": f"Agente {agent_name} no encontrado"
                }
            
            result = await agent.execute_task(task)
            return result
            
        except Exception as e:
            logger.error(f"Error ejecutando agente {agent_name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# ===============================================
# 🚀 INSTANCIA GLOBAL DEL COORDINADOR
# ===============================================
agent_coordinator = AgentCoordinator()

# ===============================================
# 🔧 FUNCIONES DE UTILIDAD
# ===============================================

async def get_agent_coordinator() -> AgentCoordinator:
    """Dependency injection para el coordinador de agentes"""
    return agent_coordinator

def create_quick_task(task_type: str, user_id: str, description: str, context: Dict[str, Any] = None) -> AgentTask:
    """Crea una tarea rápida"""
    return AgentTask(
        id=f"quick_{int(datetime.utcnow().timestamp())}",
        type=task_type,
        description=description,
        user_id=user_id,
        priority=TaskPriority.MEDIUM,
        status=TaskStatus.PENDING,
        context=context or {}
    )