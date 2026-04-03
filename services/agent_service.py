import asyncio
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from autogen import AssistantAgent, UserProxyAgent
from autogen.coding import LocalCommandLineCodeExecutor

import config
from services.tavily_search_service import tavily_search_service

logger = logging.getLogger(__name__)


@dataclass
class AgentRunResult:
    summary: str
    raw_result: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentManager:
    """
    Orquestador de agentes endurecido para producción.

    Objetivos:
    - Aislamiento por usuario.
    - No bloquear el event loop del backend.
    - Limitar concurrencia global/per-user.
    - Desactivar ejecución arbitraria de código por defecto.
    """

    def __init__(self, base_work_dir: str = "coding"):
        self.base_work_dir = Path(base_work_dir)
        self.base_work_dir.mkdir(parents=True, exist_ok=True)
        self.allow_code_execution = str(
            os.getenv("AGENT_ENABLE_CODE_EXECUTION", "false")
        ).strip().lower() in {"1", "true", "t", "yes"}
        self.max_concurrent_runs = max(1, int(os.getenv("AGENT_MAX_CONCURRENT", "4")))
        self.run_timeout_seconds = max(30, int(os.getenv("AGENT_RUN_TIMEOUT_SECONDS", "150")))
        self._global_semaphore = asyncio.Semaphore(self.max_concurrent_runs)
        self._user_locks: dict[str, asyncio.Lock] = {}

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
        user_dir = self.base_work_dir / str(user_id or "default")
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    def _get_user_lock(self, user_id: str) -> asyncio.Lock:
        key = str(user_id or "default")
        lock = self._user_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._user_locks[key] = lock
        return lock

    async def search_web(self, query: str, user_id: str = "agent_research") -> str:
        logger.info(f"Agente solicitando búsqueda web: {query}")
        results, _meta = await tavily_search_service.search_with_meta(
            query=query,
            user_id=user_id,
        )
        if not results:
            return "No se encontraron resultados relevantes en la web para esta consulta."
        formatted = []
        for r in results[:5]:
            formatted.append(
                f"- {r.get('title')}: {r.get('snippet')} (Fuente: {r.get('url')})"
            )
        return "\n".join(formatted)

    def create_team(self, user_id: str) -> tuple[UserProxyAgent, AssistantAgent]:
        user_work_dir = self._get_user_work_dir(user_id)

        assistant = AssistantAgent(
            name=f"iris_{user_id}",
            system_message=(
                "Eres el Tutor Académico de Élite. "
                "Mantén un tono natural, humano y preciso. "
                "No inventes datos, no mezcles información entre usuarios y resume el resultado final con claridad."
            ),
            llm_config=self.llm_config,
        )

        code_execution_config: Any = False
        proxy_system_message = (
            "Eres el coordinador de herramientas. "
            "Ejecuta solo lo necesario y termina cuando el asistente entregue la respuesta final."
        )
        if self.allow_code_execution:
            executor = LocalCommandLineCodeExecutor(work_dir=user_work_dir)
            code_execution_config = {
                "executor": executor,
                "last_n_messages": 2,
            }
            proxy_system_message = (
                "Eres el ejecutor. Tu única tarea es correr código aislado en el directorio del usuario. "
                "Si el código da error, detente. Si el asistente dice TERMINATE, termina."
            )

        user_proxy = UserProxyAgent(
            name=f"proxy_{user_id}",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=6,
            is_termination_msg=lambda x: "TERMINATE" in str(x.get("content", "")).upper(),
            code_execution_config=code_execution_config,
            system_message=proxy_system_message,
        )

        from autogen import register_function

        def search_web_tool(query: str) -> str:
            # AutoGen es síncrono; el chat del agente corre en un thread aparte.
            return asyncio.run(self.search_web(query, user_id=user_id))

        register_function(
            search_web_tool,
            caller=assistant,
            executor=user_proxy,
            name="search_web",
            description="Busca en internet información actualizada (precios, noticias, documentación, hechos).",
        )

        return user_proxy, assistant

    def extract_text(self, result: Any) -> str:
        if result is None:
            return ""
        if isinstance(result, AgentRunResult):
            return str(result.summary or "").strip()
        if isinstance(result, str):
            return result.strip()
        summary = getattr(result, "summary", None)
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
        chat_history = getattr(result, "chat_history", None)
        if isinstance(chat_history, list):
            for item in reversed(chat_history):
                content = item.get("content") if isinstance(item, dict) else None
                if isinstance(content, str) and content.strip():
                    return content.strip()
        if isinstance(result, dict):
            for key in ("summary", "content", "response", "text"):
                value = result.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return str(result).strip()

    def _build_full_task(self, task_description: str, history: Optional[list]) -> str:
        full_task = task_description
        if history:
            history_text = "\n".join(
                [
                    f"{str(m.get('role') or 'user').upper()}: {str(m.get('content') or '')[:300]}"
                    for m in history[-5:]
                    if isinstance(m, dict)
                ]
            )
            if history_text.strip():
                full_task = (
                    "--- CONTEXTO PREVIO DE LA CHARLA ---\n"
                    f"{history_text}\n\n"
                    "--- NUEVA TAREA ---\n"
                    f"{task_description}"
                )
        return full_task

    async def run_complex_task(
        self,
        task_description: str,
        user_id: str = "default",
        history: Optional[list] = None,
    ) -> AgentRunResult:
        """
        Ejecuta el flujo agéntico sin bloquear el loop principal.
        """

        full_task = self._build_full_task(task_description, history)
        user_lock = self._get_user_lock(user_id)
        logger.info(
            f"Iniciando tarea agéntica [USER:{user_id}] len={len(task_description or '')} allow_code_execution={self.allow_code_execution}"
        )

        def _run_sync() -> AgentRunResult:
            user_proxy, assistant = self.create_team(user_id)
            raw_result = user_proxy.initiate_chat(
                assistant,
                message=full_task,
            )
            return AgentRunResult(
                summary=self.extract_text(raw_result),
                raw_result=raw_result,
                metadata={"user_id": str(user_id)},
            )

        async with self._global_semaphore:
            async with user_lock:
                return await asyncio.wait_for(
                    asyncio.to_thread(_run_sync),
                    timeout=self.run_timeout_seconds,
                )


agent_manager = AgentManager()
