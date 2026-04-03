import os
import logging
from typing import List, Dict, Any, Optional
from autogen import AssistantAgent, UserProxyAgent
from pathlib import Path
from autogen.coding import LocalCommandLineCodeExecutor
import config

logger = logging.getLogger(__name__)

class AgentManager:
    """
    Orquestador de Nivel Dios para agentes inteligentes en el backend.
    Maneja la creación, configuración y ciclo de vida de los agentes AutoGen.
    """
    
    def __init__(self, base_work_dir: str = "coding"):
        self.base_work_dir = Path(base_work_dir)
        self.base_work_dir.mkdir(exist_ok=True)
        
        # Configuración base para Groq compatible con AutoGen
        self.llm_config = {
            "config_list": [
                {
                    "model": config.GROQ_MODEL_REASONING, 
                    "api_key": config.GROQ_API_KEY,
                    "api_type": "groq",
                }
            ],
            "cache_seed": 42,
            "temperature": config.TEMPERATURE_REASONING,
            "timeout": 120,
        }
        
    def _get_user_work_dir(self, user_id: str) -> Path:
        """Obtiene y crea el directorio de trabajo aislado para un usuario."""
        user_dir = self.base_work_dir / user_id
        user_dir.mkdir(exist_ok=True)
        return user_dir

    def create_team(self, user_id: str) -> tuple[UserProxyAgent, AssistantAgent]:
        """
        Crea un equipo básico aislado para un usuario específico.
        """
        user_work_dir = self._get_user_work_dir(user_id)
        
        # Ejecutor de código seguro e aislado
        executor = LocalCommandLineCodeExecutor(work_dir=user_work_dir)
        
        # 1. El Asistente (Cerebro)
        assistant = AssistantAgent(
            name=f"expert_{user_id}",
            system_message=f"""Eres un Ingeniero Senior de Software (Nivel Dios) para el usuario {user_id}.
            REGLAS DE ORO:
            1. Usa bloques de código con lenguaje específico: ```python ... ``` cuando generes código funcional.
            2. Sé extremadamente conciso. Prioriza la ejecución sobre las explicaciones largas.
            3. Si el código falla, analiza el error y corrige en el siguiente paso.
            4. Si la tarea está terminada con éxito, escribe 'TERMINATE'.
            5. No uses placeholders. Todo el código debe ser funcional y autónomo.
            6. Mantén la fluidez técnica basada en el contexto previo de la charla.
            
            Tu objetivo es la RESOLUCIÓN de problemas con precisión absoluta.""",
            llm_config=self.llm_config,
        )
        
        # 2. El Proxy del Usuario (Ejecutor)
        user_proxy = UserProxyAgent(
            name=f"proxy_{user_id}",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=8,  # Reducido para evitar loops infinitos y 429
            is_termination_msg=lambda x: "TERMINATE" in x.get("content", "").upper(),
            code_execution_config={
                "executor": executor,
                "last_n_messages": 2,  # Solo mirar los bloques de código recientes para evitar ruido
            },
            system_message="""Eres el ejecutor. Tu Única tarea es correr código. 
            Si el código da error, detente. Si el asistente dice TERMINATE, termina."""
        )
        
        return user_proxy, assistant

    async def run_complex_task(self, task_description: str, user_id: str = "default", history: list = None):
        """
        Inicia una sesión de colaboración aislada para un usuario con memoria contextual.
        """
        user_proxy, assistant = self.create_team(user_id)
        
        # Enriquecer el mensaje inicial con contexto del historial si existe
        full_task = task_description
        if history:
            history_text = "\n".join([f"{m['role'].upper()}: {m['content'][:300]}" for m in history[-5:]])
            full_task = f"--- CONTEXTO PREVIO DE LA CHARLA ---\n{history_text}\n\n--- NUEVA TAREA ---\n{task_description}"

        logger.info(f"Iniciando tarea agéntica con historial [USER:{user_id}]: {task_description[:50]}...")
        
        # Ejecución síncrona en hilo separado (AutoGen 0.2 es bloqueante)
        result = user_proxy.initiate_chat(
            assistant,
            message=full_task,
        )
        
        return result

# Singleton para acceso global
agent_manager = AgentManager()
