"""
Workspace Schemas - Enums y modelos Pydantic para Google Workspace Automation
Separado de workspace_orchestrator.py
"""
from datetime import datetime
from typing import Dict, Any, List, Optional
from enum import Enum
from pydantic import BaseModel, EmailStr


class WorkflowType(str, Enum):
    """Tipos de workflow soportados"""
    CONTENT_TO_DOC = "content_to_doc"
    DATA_TO_SHEET = "data_to_sheet"
    REPORT_GENERATION = "report_generation"
    PROJECT_KICKOFF = "project_kickoff"
    MEETING_SUMMARY = "meeting_summary"
    RESEARCH_REPORT = "research_report"


class AutomationRequest(BaseModel):
    """Request para ejecutar un workflow automatizado"""
    workflow_type: WorkflowType
    user_input: str
    context: Optional[Dict[str, Any]] = {}
    recipients: Optional[List[str]] = []
    folder_id: Optional[str] = None
    schedule: Optional[str] = None  # Para automatización futura


class WorkflowStep(BaseModel):
    """Paso individual dentro de un workflow"""
    step_id: str
    action: str
    status: str = "pending"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: Optional[datetime] = None


class WorkflowExecution(BaseModel):
    """Ejecución completa de un workflow"""
    execution_id: str
    workflow_type: WorkflowType
    user_email: str
    status: str = "running"
    steps: List[WorkflowStep] = []
    created_at: datetime
    completed_at: Optional[datetime] = None
    results: Dict[str, Any] = {}
