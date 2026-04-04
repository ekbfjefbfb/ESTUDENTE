"""
Workspace Orchestrator v2.0 - Refactored
Orquestador inteligente para Google Workspace Automation

Responsabilidades separadas:
- workspace_schemas.py: Enums y modelos Pydantic
- workspace_workflows.py: Handlers de workflows (6 tipos)

Este archivo es el ORQUESTADOR que coordina todo.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

from services.workspace_schemas import (
    WorkflowType, AutomationRequest, WorkflowExecution
)
from services.workspace_workflows import (
    ContentToDocWorkflow, DataToSheetWorkflow, ReportGenerationWorkflow,
    ProjectKickoffWorkflow, MeetingSummaryWorkflow, ResearchReportWorkflow
)
import json_log_formatter

# Logging
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("workspace_orchestrator")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(handler)
logger.propagate = False


class WorkspaceOrchestrator:
    """
    Orquestador inteligente para automatización de Google Workspace
    v2.0: Refactorizado - delega a handlers especializados
    """
    
    def __init__(self):
        self.active_workflows: Dict[str, WorkflowExecution] = {}
        
        # Handlers especializados por tipo de workflow
        self.workflow_handlers = {
            WorkflowType.CONTENT_TO_DOC: ContentToDocWorkflow(),
            WorkflowType.DATA_TO_SHEET: DataToSheetWorkflow(),
            WorkflowType.REPORT_GENERATION: ReportGenerationWorkflow(),
            WorkflowType.PROJECT_KICKOFF: ProjectKickoffWorkflow(),
            WorkflowType.MEETING_SUMMARY: MeetingSummaryWorkflow(),
            WorkflowType.RESEARCH_REPORT: ResearchReportWorkflow(),
        }
    
    async def execute_workflow(
        self, 
        user_email: str, 
        request: AutomationRequest
    ) -> WorkflowExecution:
        """
        Ejecuta un flujo de trabajo completo delegando al handler especializado
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
            # Obtener handler especializado
            handler = self.workflow_handlers.get(request.workflow_type)
            if not handler:
                raise ValueError(f"Workflow type not supported: {request.workflow_type}")
            
            # Ejecutar workflow
            await handler.execute(execution, request)
            
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
    
    async def get_workflow_status(self, execution_id: str) -> Optional[WorkflowExecution]:
        """Obtiene el estado de un workflow"""
        return self.active_workflows.get(execution_id)
    
    async def list_user_workflows(self, user_email: str) -> List[WorkflowExecution]:
        """Lista workflows de un usuario"""
        return [
            workflow for workflow in self.active_workflows.values()
            if workflow.user_email == user_email
        ]


# Instancia global
workspace_orchestrator = WorkspaceOrchestrator()
