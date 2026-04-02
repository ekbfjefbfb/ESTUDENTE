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
    
    def __init__(self, work_dir: str = "coding"):
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(exist_ok=True)
        
        # Configuración base para Groq compatible con AutoGen
        self.llm_config = {
            "config_list": [
                {
                    "model": config.GROQ_MODEL_REASONING, # Usamos Qwen 3 o Llama 3.3 según config
                    "api_key": config.GROQ_API_KEY,
                    "api_type": "groq",
                }
            ],
            "cache_seed": 42,  # Para consistencia en producción
            "temperature": config.TEMPERATURE_REASONING,
            "timeout": 120,
        }
        
    def create_team(self) -> tuple[UserProxyAgent, AssistantAgent]:
        """
        Crea un equipo básico de Ingeniero + Usuario Proxy.
        """
        # Ejecutor de código seguro
        executor = LocalCommandLineCodeExecutor(work_dir=self.work_dir)
        
        # 1. El Asistente (Cerebro)
        assistant = AssistantAgent(
            name="super_ai_expert",
            system_message=f"""Eres un experto en resolución de problemas nivel Senior.
            Tus capacidades:
            - Escribir código Python impecable para resolver tareas.
            - Analizar datos y generar conclusiones.
            - Colaborar con el usuario para llegar a la solución óptima.
            
            Usa el bloque de código de Python cuando sea necesario.
            Termina con 'TERMINATE' cuando la tarea esté completada.""",
            llm_config=self.llm_config,
        )
        
        # 2. El Proxy del Usuario (Ejecutor)
        user_proxy = UserProxyAgent(
            name="user_proxy",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=10,
            is_termination_msg=lambda x: x.get("content", "").rstrip().endswith("TERMINATE"),
            code_execution_config={"executor": executor},
            system_message="Actúa como el brazo ejecutor del experto. Ejecuta el código y devuelve los resultados."
        )
        
        return user_proxy, assistant

    async def run_complex_task(self, task_description: str):
        """
        Inicia una sesión de colaboración para resolver una tarea compleja.
        """
        user_proxy, assistant = self.create_team()
        
        logger.info(f"Iniciando tarea agéntica: {task_description[:50]}...")
        
        # Nota: AutoGen 0.2 es síncrono en initiate_chat, lo ejecutamos en un thread si es necesario
        # o usamos la versión asíncrona si está disponible.
        result = user_proxy.initiate_chat(
            assistant,
            message=task_description,
        )
        
        return result

# Singleton para acceso global
agent_manager = AgentManager()
