import os
import logging
from typing import List, Dict, Any, Optional
from autogen import AssistantAgent, UserProxyAgent
from pathlib import Path
from autogen.coding import LocalCommandLineCodeExecutor
import config
from services.tavily_search_service import tavily_search_service
import asyncio

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

    async def search_web(self, query: str, user_id: str = "agent_research") -> str:
        """
        Herramienta de búsqueda autónoma para el agente.
        Consulta Tavily/Serper y devuelve un resumen de los hallazgos.
        """
        logger.info(f"Agente solicitando búsqueda web: {query}")
        results, meta = await tavily_search_service.search_with_meta(query=query, user_id=user_id)
        
        if not results:
            return "No se encontraron resultados relevantes en la web para esta consulta."
            
        formatted = []
        for r in results[:5]:
            formatted.append(f"- {r.get('title')}: {r.get('snippet')} (Fuente: {r.get('url')})")
        
        return "\n".join(formatted)

    def create_team(self, user_id: str) -> tuple[UserProxyAgent, AssistantAgent]:
        """
        Crea un equipo básico aislado para un usuario específico.
        """
        user_work_dir = self._get_user_work_dir(user_id)
        
        # Ejecutor de código seguro e aislado
        executor = LocalCommandLineCodeExecutor(work_dir=user_work_dir)
        
        # 1. El Asistente (Cerebro Académico Autónomo e Increíble)
        assistant = AssistantAgent(
            name=f"expert_{user_id}",
            system_message=f"""Eres un Tutor Académico Elite (Nivel Dios). Eres el SOCIO del estudiante.
            REGLAS DE ORO:
            1. PENSAMIENTO CRÍTICO: Antes de dar la respuesta final, verifica tus cálculos matemáticos en silencio.
            2. VALOR REAL: Al final de tu explicación, ofrece siempre un "Próximo Paso Académico" o una "Perla de Sabiduría" para el estudiante.
            3. COMPRENSIBILIDAD: Si el tema es difícil, usa una ANALOGÍA de la vida real antes de las fórmulas.
            4. LENGUAJE DE SOCIO: Habla en plural ("Hagámoslo", "Lo hemos logrado"). Queremos que se sienta acompañado por alguien increíble.
            5. CLARIDAD: LaTeX ($...$) y Markdown impecable.
            6. TERMINATE: Solo escribe 'TERMINATE' cuando hayas dejado un valor real y pedagógico en el chat.
            
            Tu objetivo es transformar al estudiante y que sienta que su equipo agéntico es invencible.""",
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
        
        # --- REGISTRO DE HERRAMIENTAS (Tools) ---
        from autogen import register_function
        
        # Definir el wrapper para inyectar el user_id correcto
        def search_web_tool(query: str) -> str:
            # Dado que AutoGen 0.2.x es síncrono, corremos la tarea asíncrona de búsqueda
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Estamos en el hilo principal del backend, hay que usar threadsafe o run_sync si es bloqueante
                # Pero AutoGen corre en initiate_chat, usualmente en un thread aparte ya.
                from concurrent.futures import ThreadPoolExecutor
                import nest_asyncio
                nest_asyncio.apply()
                return loop.run_until_complete(self.search_web(query, user_id=user_id))
            else:
                return asyncio.run(self.search_web(query, user_id=user_id))

        register_function(
            search_web_tool,
            caller=assistant,
            executor=user_proxy,
            name="search_web",
            description="Busca en internet información actualizada (precios, noticias, documentación, hechos).",
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
