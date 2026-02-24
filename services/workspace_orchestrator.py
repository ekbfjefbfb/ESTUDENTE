"""
Intelligent Automation Orchestrator para Google Workspace
Sistema que automatiza flujos completos: Chat → Generate → Save → Email
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, EmailStr
import json_log_formatter
import asyncio
from enum import Enum

from services.google_workspace.google_auth_service import google_auth_service
from services.google_workspace.google_drive_service import google_drive_service
from services.google_workspace.google_docs_service import google_docs_service
from services.google_workspace.google_sheets_service import google_sheets_service
from services.google_workspace.gmail_service import gmail_service
from services.gpt_service import gpt_service
from config import AI_MODEL
from services.cache_service import smart_cache

# =============================================
# CONFIGURACIÓN DE LOGGING
# =============================================
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("workspace_orchestrator")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# =============================================
# ENUMS Y MODELOS
# =============================================

class WorkflowType(str, Enum):
    CONTENT_TO_DOC = "content_to_doc"
    DATA_TO_SHEET = "data_to_sheet"
    REPORT_GENERATION = "report_generation"
    PROJECT_KICKOFF = "project_kickoff"
    MEETING_SUMMARY = "meeting_summary"
    RESEARCH_REPORT = "research_report"

class AutomationRequest(BaseModel):
    workflow_type: WorkflowType
    user_input: str
    context: Optional[Dict[str, Any]] = {}
    recipients: Optional[List[str]] = []
    folder_id: Optional[str] = None
    schedule: Optional[str] = None  # Para automatización futura

class WorkflowStep(BaseModel):
    step_id: str
    action: str
    status: str = "pending"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: Optional[datetime] = None

class WorkflowExecution(BaseModel):
    execution_id: str
    workflow_type: WorkflowType
    user_email: str
    status: str = "running"
    steps: List[WorkflowStep] = []
    created_at: datetime
    completed_at: Optional[datetime] = None
    results: Dict[str, Any] = {}

# =============================================
# WORKSPACE ORCHESTRATOR CLASS
# =============================================

class WorkspaceOrchestrator:
    """
    Orquestador inteligente para automatización de Google Workspace
    """
    
    def __init__(self):
        self.active_workflows: Dict[str, WorkflowExecution] = {}
        
    async def execute_workflow(
        self, 
        user_email: str, 
        request: AutomationRequest
    ) -> WorkflowExecution:
        """
        Ejecuta un flujo de trabajo completo
        """
        execution_id = f"{request.workflow_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        execution = WorkflowExecution(
            execution_id=execution_id,
            workflow_type=request.workflow_type,
            user_email=user_email,
            created_at=datetime.now()
        )
        
        self.active_workflows[execution_id] = execution
        
        try:
            # Ejecutar según el tipo de workflow
            if request.workflow_type == WorkflowType.CONTENT_TO_DOC:
                await self._execute_content_to_doc(execution, request)
            elif request.workflow_type == WorkflowType.DATA_TO_SHEET:
                await self._execute_data_to_sheet(execution, request)
            elif request.workflow_type == WorkflowType.REPORT_GENERATION:
                await self._execute_report_generation(execution, request)
            elif request.workflow_type == WorkflowType.PROJECT_KICKOFF:
                await self._execute_project_kickoff(execution, request)
            elif request.workflow_type == WorkflowType.MEETING_SUMMARY:
                await self._execute_meeting_summary(execution, request)
            elif request.workflow_type == WorkflowType.RESEARCH_REPORT:
                await self._execute_research_report(execution, request)
            
            execution.status = "completed"
            execution.completed_at = datetime.now()
            
            logger.info({
                "event": "workflow_completed",
                "execution_id": execution_id,
                "workflow_type": request.workflow_type,
                "user_email": user_email
            })
            
        except Exception as e:
            execution.status = "failed"
            execution.completed_at = datetime.now()
            
            logger.error({
                "event": "workflow_failed",
                "execution_id": execution_id,
                "error": str(e),
                "user_email": user_email
            })
            
            raise
        
        return execution
    
    async def _execute_content_to_doc(
        self, 
        execution: WorkflowExecution, 
        request: AutomationRequest
    ):
        """
        Flujo: User Input → GPT Enhancement → Google Doc → Email Notification
        """
        user_email = execution.user_email
        
        # Step 1: Mejorar contenido con GPT
        step1 = WorkflowStep(
            step_id="enhance_content",
            action="Enhancing content with AI",
            timestamp=datetime.now()
        )
        execution.steps.append(step1)
        
        try:
            enhanced_content = await gpt_service.chat_completion(
                user_email=user_email,
                messages=[{
                    "role": "user",
                    "content": f"""
                    Por favor mejora y estructura el siguiente contenido para un documento profesional:
                    
                    {request.user_input}
                    
                    Agrega:
                    - Título apropiado
                    - Estructura clara con encabezados
                    - Mejor redacción y formato
                    - Conclusiones si es necesario
                    """
                }],
                # IA Local con DeepSeek-VL
                fast_reasoning=True,
                search_live=True
            )
            
            step1.status = "completed"
            step1.result = {"enhanced_content": enhanced_content}
            
        except Exception as e:
            step1.status = "failed"
            step1.error = str(e)
            raise
        
        # Step 2: Crear documento en Google Docs
        step2 = WorkflowStep(
            step_id="create_document",
            action="Creating Google Document",
            timestamp=datetime.now()
        )
        execution.steps.append(step2)
        
        try:
            # Extraer título del contenido mejorado
            title = f"Document - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            if "# " in enhanced_content:
                title_line = [line for line in enhanced_content.split('\n') if line.startswith('# ')][0]
                title = title_line.replace('# ', '').strip()
            
            doc_info = await google_docs_service.create_document(
                user_email, title, template="professional", folder_id=request.folder_id
            )
            
            # Agregar contenido
            await google_docs_service.add_content(
                user_email, doc_info['id'], enhanced_content
            )
            
            step2.status = "completed"
            step2.result = {"document": doc_info}
            execution.results["document"] = doc_info
            
        except Exception as e:
            step2.status = "failed"
            step2.error = str(e)
            raise
        
        # Step 3: Enviar notificación por email (si hay recipients)
        if request.recipients:
            step3 = WorkflowStep(
                step_id="send_notification",
                action="Sending email notification",
                timestamp=datetime.now()
            )
            execution.steps.append(step3)
            
            try:
                email_result = await gmail_service.send_document_notification(
                    user_email, request.recipients, doc_info
                )
                
                step3.status = "completed"
                step3.result = {"email": email_result}
                execution.results["email"] = email_result
                
            except Exception as e:
                step3.status = "failed"
                step3.error = str(e)
                # No fallar todo el workflow por email
                logger.warning(f"Email notification failed: {e}")
    
    async def _execute_data_to_sheet(
        self, 
        execution: WorkflowExecution, 
        request: AutomationRequest
    ):
        """
        Flujo: Data Input → Process with GPT → Google Sheets → Analytics
        """
        user_email = execution.user_email
        
        # Step 1: Procesar y estructurar datos
        step1 = WorkflowStep(
            step_id="process_data",
            action="Processing data with AI",
            timestamp=datetime.now()
        )
        execution.steps.append(step1)
        
        try:
            processed_data = await gpt_service.chat_completion(
                user_email=user_email,
                messages=[{
                    "role": "user",
                    "content": f"""
                    Analiza los siguientes datos y crea una estructura tabular apropiada para Google Sheets:
                    
                    {request.user_input}
                    
                    Responde con:
                    1. Un título para la hoja de cálculo
                    2. Headers de columnas apropiados
                    3. Datos organizados en filas
                    4. Sugerencias de fórmulas o gráficos
                    
                    Formato JSON por favor.
                    """
                }],
                model=AI_MODEL
            )
            
            step1.status = "completed"
            step1.result = {"processed_data": processed_data}
            
        except Exception as e:
            step1.status = "failed"
            step1.error = str(e)
            raise
        
        # Step 2: Crear spreadsheet
        step2 = WorkflowStep(
            step_id="create_spreadsheet",
            action="Creating Google Spreadsheet",
            timestamp=datetime.now()
        )
        execution.steps.append(step2)
        
        try:
            sheet_title = f"Data Analysis - {datetime.now().strftime('%Y-%m-%d')}"
            
            sheet_info = await google_sheets_service.create_spreadsheet(
                user_email, sheet_title, template="analytics", folder_id=request.folder_id
            )
            
            # Aquí procesaríamos el JSON de GPT para extraer datos
            # Por simplicidad, usamos datos de ejemplo
            headers = ["Item", "Value", "Category", "Date"]
            sample_data = [headers, ["Sample 1", "100", "Type A", "2024-01-01"]]
            
            await google_sheets_service.write_data(
                user_email, sheet_info['spreadsheet_id'], "A1:D2", sample_data
            )
            
            step2.status = "completed"
            step2.result = {"spreadsheet": sheet_info}
            execution.results["spreadsheet"] = sheet_info
            
        except Exception as e:
            step2.status = "failed"
            step2.error = str(e)
            raise
    
    async def _execute_report_generation(
        self, 
        execution: WorkflowExecution, 
        request: AutomationRequest
    ):
        """
        Flujo completo: Research → Document → Spreadsheet → Email Report
        """
        user_email = execution.user_email
        
        # Step 1: Generar reporte con IA
        step1 = WorkflowStep(
            step_id="generate_report",
            action="Generating comprehensive report",
            timestamp=datetime.now()
        )
        execution.steps.append(step1)
        
        try:
            report_content = await gpt_service.chat_completion(
                user_email=user_email,
                messages=[{
                    "role": "user",
                    "content": f"""
                    Genera un reporte completo y profesional sobre:
                    {request.user_input}
                    
                    Incluye:
                    - Executive Summary
                    - Análisis detallado
                    - Datos y métricas relevantes
                    - Conclusiones y recomendaciones
                    - Próximos pasos
                    
                    Formato Markdown profesional.
                    """
                }],
                model=AI_MODEL
            )
            
            step1.status = "completed"
            step1.result = {"report_content": report_content}
            
        except Exception as e:
            step1.status = "failed"
            step1.error = str(e)
            raise
        
        # Step 2: Crear documento del reporte
        step2 = WorkflowStep(
            step_id="create_report_doc",
            action="Creating report document",
            timestamp=datetime.now()
        )
        execution.steps.append(step2)
        
        try:
            report_title = f"Report - {datetime.now().strftime('%Y-%m-%d')}"
            
            doc_info = await google_docs_service.create_document(
                user_email, report_title, template="report", folder_id=request.folder_id
            )
            
            await google_docs_service.add_content(
                user_email, doc_info['id'], report_content
            )
            
            step2.status = "completed"
            step2.result = {"document": doc_info}
            execution.results["document"] = doc_info
            
        except Exception as e:
            step2.status = "failed"
            step2.error = str(e)
            raise
        
        # Step 3: Crear hoja de datos (si aplica)
        step3 = WorkflowStep(
            step_id="create_data_sheet",
            action="Creating data analysis sheet",
            timestamp=datetime.now()
        )
        execution.steps.append(step3)
        
        try:
            sheet_title = f"Report Data - {datetime.now().strftime('%Y-%m-%d')}"
            
            sheet_info = await google_sheets_service.create_spreadsheet(
                user_email, sheet_title, template="report_data", folder_id=request.folder_id
            )
            
            step3.status = "completed"
            step3.result = {"spreadsheet": sheet_info}
            execution.results["spreadsheet"] = sheet_info
            
        except Exception as e:
            step3.status = "failed"
            step3.error = str(e)
            # No fallar todo por esto
            logger.warning(f"Data sheet creation failed: {e}")
        
        # Step 4: Enviar reporte por email
        if request.recipients:
            step4 = WorkflowStep(
                step_id="send_report",
                action="Sending report via email",
                timestamp=datetime.now()
            )
            execution.steps.append(step4)
            
            try:
                email_result = await gmail_service.send_email(
                    user_email=user_email,
                    to_emails=request.recipients,
                    subject=f"Report: {report_title}",
                    body=f"Please find the generated report attached.",
                    html_body=f"""
                    <h2>Report Generated</h2>
                    <p>A comprehensive report has been generated and is available in your Google Drive.</p>
                    <p><strong>Document:</strong> <a href="{doc_info.get('url', '#')}">View Report</a></p>
                    <p>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
                    """,
                    attachments=[{
                        "file_id": doc_info['id'],
                        "name": f"{report_title}.pdf"
                    }] if doc_info else None
                )
                
                step4.status = "completed"
                step4.result = {"email": email_result}
                execution.results["email"] = email_result
                
            except Exception as e:
                step4.status = "failed"
                step4.error = str(e)
                logger.warning(f"Report email failed: {e}")
    
    async def _execute_project_kickoff(
        self, 
        execution: WorkflowExecution, 
        request: AutomationRequest
    ):
        """
        Flujo: Project Brief → Create Project Structure → Documents → Team Notification
        """
        user_email = execution.user_email
        
        # Step 1: Crear estructura de proyecto
        step1 = WorkflowStep(
            step_id="create_project_structure",
            action="Creating project structure",
            timestamp=datetime.now()
        )
        execution.steps.append(step1)
        
        try:
            project_name = request.context.get('project_name', f"Project {datetime.now().strftime('%Y%m%d')}")
            
            project_structure = await google_drive_service.create_project_structure(
                user_email, project_name
            )
            
            step1.status = "completed"
            step1.result = {"project_structure": project_structure}
            execution.results["project"] = project_structure
            
        except Exception as e:
            step1.status = "failed"
            step1.error = str(e)
            raise
        
        # Step 2: Crear documentos base del proyecto
        step2 = WorkflowStep(
            step_id="create_project_docs",
            action="Creating project documents",
            timestamp=datetime.now()
        )
        execution.steps.append(step2)
        
        try:
            docs_folder_id = project_structure['folders']['docs']['id']
            
            # Documento de planificación
            planning_doc = await google_docs_service.create_document(
                user_email, f"{project_name} - Planning", 
                template="project_planning", folder_id=docs_folder_id
            )
            
            # Agregar brief del proyecto
            await google_docs_service.add_content(
                user_email, planning_doc['id'], request.user_input
            )
            
            step2.status = "completed"
            step2.result = {"planning_doc": planning_doc}
            execution.results["planning_doc"] = planning_doc
            
        except Exception as e:
            step2.status = "failed"
            step2.error = str(e)
            raise
    
    async def _execute_meeting_summary(
        self, 
        execution: WorkflowExecution, 
        request: AutomationRequest
    ):
        """
        Flujo: Meeting Notes → AI Summary → Document → Action Items Sheet → Email
        """
        # Similar implementation para meeting summaries
        pass
    
    async def _execute_research_report(
        self, 
        execution: WorkflowExecution, 
        request: AutomationRequest
    ):
        """
        Flujo: Research Topic → AI Research → Comprehensive Report → Data Sheet → Distribution
        """
        # Similar implementation para research reports
        pass
    
    async def get_workflow_status(self, execution_id: str) -> Optional[WorkflowExecution]:
        """
        Obtiene el estado de un workflow
        """
        return self.active_workflows.get(execution_id)
    
    async def list_user_workflows(self, user_email: str) -> List[WorkflowExecution]:
        """
        Lista workflows de un usuario
        """
        return [
            workflow for workflow in self.active_workflows.values()
            if workflow.user_email == user_email
        ]

# =============================================
# INSTANCIA GLOBAL
# =============================================

workspace_orchestrator = WorkspaceOrchestrator()