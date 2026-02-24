"""
🧪 Tests Completos para Sistema de Agentes
==========================================
Cobertura: PersonalAgent, DocumentAgent, ImageAgent, DataAgent
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

# Importar componentes del sistema de agentes
from services.agents_system import (
    PersonalAgent,
    DocumentAgent,
    ImageAgent,
    DataAgent,
    AgentTask,
    AgentType,
    TaskPriority,
    TaskStatus,
    AgentCapability
)


class TestPersonalAgent:
    """Tests para PersonalAgent (Coordinador)"""
    
    @pytest.fixture
    def personal_agent(self):
        """Fixture para crear PersonalAgent"""
        return PersonalAgent(agent_id="test_personal_001")
    
    @pytest.mark.asyncio
    async def test_agent_initialization(self, personal_agent):
        """Test: Agente se inicializa correctamente"""
        assert personal_agent.agent_id == "test_personal_001"
        assert personal_agent.agent_type == AgentType.PERSONAL
        assert personal_agent.is_active is True
        assert len(personal_agent.current_tasks) == 0
        assert personal_agent.completed_tasks_count == 0
    
    @pytest.mark.asyncio
    async def test_get_capabilities(self, personal_agent):
        """Test: PersonalAgent retorna capacidades correctas"""
        capabilities = await personal_agent.get_capabilities()
        
        assert len(capabilities) >= 3
        assert any(c.name == "task_coordination" for c in capabilities)
        assert any(c.name == "request_analysis" for c in capabilities)
        assert any(c.name == "result_assembly" for c in capabilities)
        
        # Verificar confidence scores
        coord_cap = next(c for c in capabilities if c.name == "task_coordination")
        assert coord_cap.confidence_score >= 0.9
    
    @pytest.mark.asyncio
    async def test_can_handle_coordination_task(self, personal_agent):
        """Test: PersonalAgent puede manejar tareas de coordinación"""
        task = AgentTask(
            id="task_001",
            type="coordinate_multi_agent",
            description="Coordinar análisis complejo",
            user_id="user_123",
            priority=TaskPriority.HIGH,
            status=TaskStatus.PENDING
        )
        
        can_handle = await personal_agent.can_handle_task(task)
        assert can_handle is True
    
    @pytest.mark.asyncio
    async def test_cannot_handle_specialized_task(self, personal_agent):
        """Test: PersonalAgent no maneja tareas especializadas directamente"""
        task = AgentTask(
            id="task_002",
            type="ocr_extraction",
            description="Extraer texto de PDF",
            user_id="user_123",
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.PENDING
        )
        
        can_handle = await personal_agent.can_handle_task(task)
        assert can_handle is False
    
    @pytest.mark.asyncio
    async def test_accept_task_success(self, personal_agent):
        """Test: PersonalAgent acepta tarea válida"""
        task = AgentTask(
            id="task_003",
            type="analyze_request",
            description="Analizar solicitud de usuario",
            user_id="user_123",
            priority=TaskPriority.HIGH,
            status=TaskStatus.PENDING
        )
        
        accepted = await personal_agent.accept_task(task)
        
        assert accepted is True
        assert task.status == TaskStatus.IN_PROGRESS
        assert task.assigned_agent == "test_personal_001"
        assert "task_003" in personal_agent.current_tasks
    
    @pytest.mark.asyncio
    async def test_reject_task_when_overloaded(self, personal_agent):
        """Test: PersonalAgent rechaza tareas cuando está sobrecargado"""
        # Llenar el agente hasta el máximo
        for i in range(personal_agent.max_concurrent_tasks):
            task = AgentTask(
                id=f"task_{i}",
                type="analyze_request",
                description=f"Tarea {i}",
                user_id="user_123",
                priority=TaskPriority.MEDIUM,
                status=TaskStatus.PENDING
            )
            await personal_agent.accept_task(task)
        
        # Intentar agregar una tarea más
        overflow_task = AgentTask(
            id="task_overflow",
            type="analyze_request",
            description="Tarea extra",
            user_id="user_123",
            priority=TaskPriority.LOW,
            status=TaskStatus.PENDING
        )
        
        accepted = await personal_agent.accept_task(overflow_task)
        assert accepted is False
    
    @pytest.mark.asyncio
    async def test_register_specialized_agent(self, personal_agent):
        """Test: PersonalAgent registra agentes especializados"""
        doc_agent = DocumentAgent(agent_id="doc_001")
        personal_agent.register_specialized_agent(doc_agent)
        
        assert AgentType.DOCUMENT in personal_agent.specialized_agents
        assert personal_agent.specialized_agents[AgentType.DOCUMENT] == doc_agent
    
    @pytest.mark.asyncio
    async def test_get_status(self, personal_agent):
        """Test: PersonalAgent retorna estado correcto"""
        # Agregar algunas tareas
        for i in range(3):
            task = AgentTask(
                id=f"task_{i}",
                type="analyze_request",
                description=f"Tarea {i}",
                user_id="user_123",
                priority=TaskPriority.MEDIUM,
                status=TaskStatus.PENDING
            )
            await personal_agent.accept_task(task)
        
        status = personal_agent.get_status()
        
        assert status["agent_id"] == "test_personal_001"
        assert status["agent_type"] == "personal"
        assert status["is_active"] is True
        assert status["current_tasks"] == 3
        assert status["load_percentage"] == 30.0  # 3/10 * 100


class TestDocumentAgent:
    """Tests para DocumentAgent"""
    
    @pytest.fixture
    def document_agent(self):
        """Fixture para crear DocumentAgent"""
        return DocumentAgent(agent_id="test_doc_001")
    
    @pytest.mark.asyncio
    async def test_document_agent_initialization(self, document_agent):
        """Test: DocumentAgent se inicializa correctamente"""
        assert document_agent.agent_id == "test_doc_001"
        assert document_agent.agent_type == AgentType.DOCUMENT
        assert document_agent.is_active is True
    
    @pytest.mark.asyncio
    async def test_can_handle_pdf_task(self, document_agent):
        """Test: DocumentAgent puede manejar PDFs"""
        task = AgentTask(
            id="task_pdf",
            type="pdf_processing",
            description="Procesar PDF de 10 páginas",
            user_id="user_123",
            priority=TaskPriority.HIGH,
            status=TaskStatus.PENDING,
            context={"file_type": "pdf", "pages": 10}
        )
        
        can_handle = await document_agent.can_handle_task(task)
        assert can_handle is True
    
    @pytest.mark.asyncio
    async def test_can_handle_ocr_task(self, document_agent):
        """Test: DocumentAgent puede manejar OCR"""
        task = AgentTask(
            id="task_ocr",
            type="ocr_extraction",
            description="OCR de documento escaneado",
            user_id="user_123",
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.PENDING,
            context={"file_type": "image", "language": "es"}
        )
        
        can_handle = await document_agent.can_handle_task(task)
        assert can_handle is True
    
    @pytest.mark.asyncio
    async def test_cannot_handle_image_generation(self, document_agent):
        """Test: DocumentAgent no maneja generación de imágenes"""
        task = AgentTask(
            id="task_img",
            type="image_generation",
            description="Generar imagen",
            user_id="user_123",
            priority=TaskPriority.LOW,
            status=TaskStatus.PENDING
        )
        
        can_handle = await document_agent.can_handle_task(task)
        assert can_handle is False


class TestImageAgent:
    """Tests para ImageAgent"""
    
    @pytest.fixture
    def image_agent(self):
        """Fixture para crear ImageAgent"""
        return ImageAgent(agent_id="test_img_001")
    
    @pytest.mark.asyncio
    async def test_image_agent_initialization(self, image_agent):
        """Test: ImageAgent se inicializa correctamente"""
        assert image_agent.agent_id == "test_img_001"
        assert image_agent.agent_type == AgentType.IMAGE
        assert image_agent.is_active is True
    
    @pytest.mark.asyncio
    async def test_can_handle_image_generation(self, image_agent):
        """Test: ImageAgent puede generar imágenes"""
        task = AgentTask(
            id="task_gen",
            type="image_generation",
            description="Generar logo moderno",
            user_id="user_123",
            priority=TaskPriority.HIGH,
            status=TaskStatus.PENDING,
            context={
                "prompt": "Modern tech company logo",
                "size": "1024x1024",
                "style": "minimalist"
            }
        )
        
        can_handle = await image_agent.can_handle_task(task)
        assert can_handle is True
    
    @pytest.mark.asyncio
    async def test_can_handle_object_detection(self, image_agent):
        """Test: ImageAgent puede detectar objetos"""
        task = AgentTask(
            id="task_detect",
            type="object_detection",
            description="Detectar objetos en imagen",
            user_id="user_123",
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.PENDING,
            context={"image_url": "https://example.com/image.jpg"}
        )
        
        can_handle = await image_agent.can_handle_task(task)
        assert can_handle is True


class TestDataAgent:
    """Tests para DataAgent"""
    
    @pytest.fixture
    def data_agent(self):
        """Fixture para crear DataAgent"""
        return DataAgent(agent_id="test_data_001")
    
    @pytest.mark.asyncio
    async def test_data_agent_initialization(self, data_agent):
        """Test: DataAgent se inicializa correctamente"""
        assert data_agent.agent_id == "test_data_001"
        assert data_agent.agent_type == AgentType.DATA
        assert data_agent.is_active is True
    
    @pytest.mark.asyncio
    async def test_can_handle_data_analysis(self, data_agent):
        """Test: DataAgent puede analizar datos"""
        task = AgentTask(
            id="task_analysis",
            type="data_analysis",
            description="Analizar datos de ventas",
            user_id="user_123",
            priority=TaskPriority.HIGH,
            status=TaskStatus.PENDING,
            context={
                "data_source": "sales_csv",
                "analysis_type": "descriptive"
            }
        )
        
        can_handle = await data_agent.can_handle_task(task)
        assert can_handle is True
    
    @pytest.mark.asyncio
    async def test_can_handle_visualization(self, data_agent):
        """Test: DataAgent puede crear visualizaciones"""
        task = AgentTask(
            id="task_viz",
            type="visualization",
            description="Crear gráfico de barras",
            user_id="user_123",
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.PENDING,
            context={
                "chart_type": "bar",
                "data": [10, 20, 30, 40]
            }
        )
        
        can_handle = await data_agent.can_handle_task(task)
        assert can_handle is True


class TestAgentCoordination:
    """Tests para coordinación multi-agente"""
    
    @pytest.fixture
    def agent_system(self):
        """Fixture para sistema completo de agentes"""
        personal = PersonalAgent(agent_id="coord_001")
        document = DocumentAgent(agent_id="doc_001")
        image = ImageAgent(agent_id="img_001")
        data = DataAgent(agent_id="data_001")
        
        # Registrar agentes especializados
        personal.register_specialized_agent(document)
        personal.register_specialized_agent(image)
        personal.register_specialized_agent(data)
        
        return {
            "personal": personal,
            "document": document,
            "image": image,
            "data": data
        }
    
    @pytest.mark.asyncio
    async def test_multi_agent_coordination(self, agent_system):
        """Test: Coordinación entre múltiples agentes"""
        personal = agent_system["personal"]
        
        # Verificar que todos los agentes están registrados
        assert len(personal.specialized_agents) == 3
        assert AgentType.DOCUMENT in personal.specialized_agents
        assert AgentType.IMAGE in personal.specialized_agents
        assert AgentType.DATA in personal.specialized_agents
    
    @pytest.mark.asyncio
    async def test_task_delegation_flow(self, agent_system):
        """Test: Flujo de delegación de tareas"""
        personal = agent_system["personal"]
        document = agent_system["document"]
        
        # Crear tarea que requiere DocumentAgent
        task = AgentTask(
            id="task_delegate",
            type="pdf_processing",
            description="Procesar PDF complejo",
            user_id="user_123",
            priority=TaskPriority.HIGH,
            status=TaskStatus.PENDING
        )
        
        # DocumentAgent debe poder manejarla
        can_handle = await document.can_handle_task(task)
        assert can_handle is True
        
        # DocumentAgent acepta la tarea
        accepted = await document.accept_task(task)
        assert accepted is True
        assert task.status == TaskStatus.IN_PROGRESS
        assert task.assigned_agent == "doc_001"


class TestAgentMetrics:
    """Tests para métricas de agentes"""
    
    @pytest.fixture
    def personal_agent(self):
        return PersonalAgent(agent_id="metrics_001")
    
    @pytest.mark.asyncio
    async def test_task_completion_increments_counter(self, personal_agent):
        """Test: Completar tarea incrementa contador"""
        initial_count = personal_agent.completed_tasks_count
        
        task = AgentTask(
            id="task_metric",
            type="analyze_request",
            description="Tarea de prueba",
            user_id="user_123",
            priority=TaskPriority.LOW,
            status=TaskStatus.PENDING
        )
        
        await personal_agent.accept_task(task)
        
        # Mock del resultado
        with patch.object(personal_agent, 'process_task', 
                          return_value={"status": "success"}):
            await personal_agent.execute_task(task)
        
        assert personal_agent.completed_tasks_count == initial_count + 1
    
    @pytest.mark.asyncio
    async def test_task_failure_increments_counter(self, personal_agent):
        """Test: Fallo de tarea incrementa contador de fallos"""
        initial_count = personal_agent.failed_tasks_count
        
        task = AgentTask(
            id="task_fail",
            type="analyze_request",
            description="Tarea que fallará",
            user_id="user_123",
            priority=TaskPriority.LOW,
            status=TaskStatus.PENDING
        )
        
        await personal_agent.accept_task(task)
        
        # Mock que lanza excepción
        with patch.object(personal_agent, 'process_task', 
                          side_effect=Exception("Test error")):
            with pytest.raises(Exception):
                await personal_agent.execute_task(task)
        
        assert personal_agent.failed_tasks_count == initial_count + 1
        assert task.status == TaskStatus.FAILED
        assert task.error == "Test error"


class TestAgentTask:
    """Tests para modelo AgentTask"""
    
    def test_task_creation(self):
        """Test: Crear AgentTask con valores correctos"""
        task = AgentTask(
            id="task_001",
            type="test_task",
            description="Tarea de prueba",
            user_id="user_123",
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.PENDING
        )
        
        assert task.id == "task_001"
        assert task.type == "test_task"
        assert task.priority == TaskPriority.MEDIUM
        assert task.status == TaskStatus.PENDING
        assert task.created_at is not None
        assert isinstance(task.created_at, datetime)
    
    def test_task_with_context(self):
        """Test: AgentTask con contexto adicional"""
        context = {
            "file_type": "pdf",
            "pages": 10,
            "language": "es"
        }
        
        task = AgentTask(
            id="task_context",
            type="pdf_processing",
            description="PDF con contexto",
            user_id="user_123",
            priority=TaskPriority.HIGH,
            status=TaskStatus.PENDING,
            context=context
        )
        
        assert task.context == context
        assert task.context["file_type"] == "pdf"
        assert task.context["pages"] == 10


class TestAgentCapability:
    """Tests para capacidades de agentes"""
    
    def test_capability_creation(self):
        """Test: Crear AgentCapability"""
        capability = AgentCapability(
            name="test_capability",
            description="Capacidad de prueba",
            supported_formats=["pdf", "docx"],
            confidence_score=0.95,
            max_concurrent_tasks=5
        )
        
        assert capability.name == "test_capability"
        assert capability.confidence_score == 0.95
        assert "pdf" in capability.supported_formats
        assert capability.max_concurrent_tasks == 5


# ===============================================
# TESTS DE INTEGRACIÓN
# ===============================================

class TestAgentSystemIntegration:
    """Tests de integración del sistema completo"""
    
    @pytest.mark.asyncio
    async def test_full_workflow_document_processing(self):
        """Test: Flujo completo de procesamiento de documento"""
        # Setup
        personal = PersonalAgent(agent_id="integration_personal")
        document = DocumentAgent(agent_id="integration_doc")
        personal.register_specialized_agent(document)
        
        # Simular solicitud de usuario
        user_request = "Analizar PDF de 5 páginas y extraer tablas"
        
        # PersonalAgent analiza y delega
        task = AgentTask(
            id="integration_task_001",
            type="pdf_processing",
            description=user_request,
            user_id="user_integration",
            priority=TaskPriority.HIGH,
            status=TaskStatus.PENDING,
            context={"file_type": "pdf", "pages": 5}
        )
        
        # DocumentAgent acepta
        can_handle = await document.can_handle_task(task)
        assert can_handle is True
        
        accepted = await document.accept_task(task)
        assert accepted is True
        
        # Verificar estado
        assert task.status == TaskStatus.IN_PROGRESS
        assert "integration_task_001" in document.current_tasks
    
    @pytest.mark.asyncio
    async def test_parallel_agent_execution(self):
        """Test: Ejecución paralela de múltiples agentes"""
        # Setup
        personal = PersonalAgent(agent_id="parallel_coord")
        doc1 = DocumentAgent(agent_id="parallel_doc1")
        doc2 = DocumentAgent(agent_id="parallel_doc2")
        img1 = ImageAgent(agent_id="parallel_img1")
        
        personal.register_specialized_agent(doc1)
        personal.register_specialized_agent(img1)
        
        # Crear múltiples tareas
        tasks = [
            AgentTask(
                id=f"parallel_task_{i}",
                type="pdf_processing" if i < 2 else "image_generation",
                description=f"Tarea paralela {i}",
                user_id="user_parallel",
                priority=TaskPriority.MEDIUM,
                status=TaskStatus.PENDING
            )
            for i in range(3)
        ]
        
        # Asignar tareas
        await doc1.accept_task(tasks[0])
        await doc2.accept_task(tasks[1])
        await img1.accept_task(tasks[2])
        
        # Verificar que todas están en progreso
        assert all(t.status == TaskStatus.IN_PROGRESS for t in tasks)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
