"""
Workspace Workflows - Handlers para cada tipo de workflow
Separado de workspace_orchestrator.py
"""
import logging
from datetime import datetime

# Imports fail-safe para servicios opcionales
try:
    from services.gpt_service import gpt_service
    GPT_SERVICE_AVAILABLE = True
except Exception:
    gpt_service = None
    GPT_SERVICE_AVAILABLE = False

try:
    from services.google_workspace.google_docs_service import google_docs_service
    DOCS_SERVICE_AVAILABLE = True
except Exception:
    google_docs_service = None
    DOCS_SERVICE_AVAILABLE = False

try:
    from services.google_workspace.google_sheets_service import google_sheets_service
    SHEETS_SERVICE_AVAILABLE = True
except Exception:
    google_sheets_service = None
    SHEETS_SERVICE_AVAILABLE = False

try:
    from services.google_workspace.google_drive_service import google_drive_service
    DRIVE_SERVICE_AVAILABLE = True
except Exception:
    google_drive_service = None
    DRIVE_SERVICE_AVAILABLE = False

try:
    from services.google_workspace.gmail_service import gmail_service
    GMAIL_SERVICE_AVAILABLE = True
except Exception:
    gmail_service = None
    GMAIL_SERVICE_AVAILABLE = False

from config import AI_MODEL
from services.workspace_schemas import WorkflowExecution, AutomationRequest, WorkflowStep

logger = logging.getLogger("workspace_workflows")


class ContentToDocWorkflow:
    """Workflow: User Input → GPT Enhancement → Google Doc → Email Notification"""
    
    async def execute(self, execution: WorkflowExecution, request: AutomationRequest):
        user_email = execution.user_email
        
        if not GPT_SERVICE_AVAILABLE:
            logger.error("gpt_service no disponible")
            raise RuntimeError("gpt_service_unavailable")
        
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
            title = f"Document - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            if "# " in enhanced_content:
                title_line = [line for line in enhanced_content.split('\n') if line.startswith('# ')][0]
                title = title_line.replace('# ', '').strip()
            
            doc_info = await google_docs_service.create_document(
                user_email, title, template="professional", folder_id=request.folder_id
            )
            
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
        
        # Step 3: Enviar notificación por email
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
                logger.warning(f"Email notification failed: {e}")


class DataToSheetWorkflow:
    """Workflow: Data Input → Process with GPT → Google Sheets → Analytics"""
    
    async def execute(self, execution: WorkflowExecution, request: AutomationRequest):
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


class ReportGenerationWorkflow:
    """Workflow: Research → Document → Spreadsheet → Email Report"""
    
    async def execute(self, execution: WorkflowExecution, request: AutomationRequest):
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
        
        # Step 3: Crear hoja de datos
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
                    body="Please find the generated report attached.",
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


class ProjectKickoffWorkflow:
    """Workflow: Project Brief → Create Project Structure → Documents → Team Notification"""
    
    async def execute(self, execution: WorkflowExecution, request: AutomationRequest):
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
            
            planning_doc = await google_docs_service.create_document(
                user_email, f"{project_name} - Planning", 
                template="project_planning", folder_id=docs_folder_id
            )
            
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


class MeetingSummaryWorkflow:
    """Workflow: Meeting Notes → AI Summary → Document → Action Items Sheet → Email"""
    
    async def execute(self, execution: WorkflowExecution, request: AutomationRequest):
        """Placeholder para implementación futura"""
        logger.info("MeetingSummaryWorkflow: Not yet implemented")
        execution.results["note"] = "Meeting summary workflow not yet implemented"


class ResearchReportWorkflow:
    """Workflow: Research Topic → AI Research → Comprehensive Report → Data Sheet → Distribution"""
    
    async def execute(self, execution: WorkflowExecution, request: AutomationRequest):
        """Placeholder para implementación futura"""
        logger.info("ResearchReportWorkflow: Not yet implemented")
        execution.results["note"] = "Research report workflow not yet implemented"
