import logging
import os
import re
from typing import Optional

from groq import Groq

import config

logger = logging.getLogger(__name__)

_GREETING_RE = re.compile(
    r"^\s*(hola|hello|hi|buenas|buenos dias|buenas tardes|buenas noches|gracias|ok|vale)\b",
    re.IGNORECASE,
)
_AGENT_TRIGGER_RE = re.compile(
    (
        r"\b("
        r"demuestra|resolver|resuelve|paso a paso|explica|explicame|explicación|analiza|investiga|"
        r"arquitectura|refactor|debug|bug|error|traceback|sql|api|websocket|backend|flutter|"
        r"modelo|algoritmo|demostración|simulación|simulacion|cálculo|calculo|física|fisica|"
        r"estadística|estadistica|prueba técnica|prueba tecnica|documentación|documentacion"
        r")\b"
    ),
    re.IGNORECASE,
)


class ScoutOrchestrator:
    """
    Clasificador de ruta rápido y estable.

    Prioriza heurísticas locales para no añadir una llamada extra al modelo en cada request.
    Solo usa un clasificador remoto si el caso es ambiguo y está habilitado explícitamente.
    """

    def __init__(self):
        self.model = config.GROQ_MODEL_FAST
        self.remote_enabled = str(
            os.getenv("SCOUT_USE_REMOTE_CLASSIFIER", "false")
        ).strip().lower() in {"1", "true", "t", "yes"}
        self.client: Optional[Groq] = None
        if self.remote_enabled and config.GROQ_API_KEY:
            try:
                self.client = Groq(api_key=config.GROQ_API_KEY)
            except Exception as exc:
                logger.warning(f"Scout remoto deshabilitado: {exc}")
                self.client = None

    def _should_use_agents_local(self, user_message: str, history: Optional[list]) -> Optional[bool]:
        text = str(user_message or "").strip()
        if not text:
            return False

        lowered = text.lower()
        if len(text) <= 24 and _GREETING_RE.search(text):
            return False

        if len(text) >= 450:
            return True

        if _AGENT_TRIGGER_RE.search(text):
            return True

        if "```" in text or any(token in lowered for token in ("\ndef ", "\nclass ", "traceback", "stack trace")):
            return True

        if history:
            history_tail = " ".join(
                str(item.get("content") or "")[:120]
                for item in history[-2:]
                if isinstance(item, dict)
            ).lower()
            if history_tail and _AGENT_TRIGGER_RE.search(history_tail) and len(text) <= 120:
                return True

        if len(text) <= 80:
            return False

        return None

    def _should_use_agents_remote(self, user_message: str, history: Optional[list]) -> bool:
        if self.client is None:
            return False

        history_context = ""
        if history:
            history_text = "\n".join(
                [
                    f"{str(m.get('role') or 'user').upper()}: {str(m.get('content') or '')[:100]}"
                    for m in history[-3:]
                    if isinstance(m, dict)
                ]
            )
            if history_text:
                history_context = f"\nContexto reciente:\n{history_text}\n"

        prompt = f"""Responde 'AGENT' solo si requiere:
        - Resolver problemas matemáticos o científicos complejos.
        - Explicar conceptos técnicos paso a paso.
        - Investigar datos técnicos o históricos actuales.
        - Diseñar o depurar código/arquitectura.
        {history_context}
        De lo contrario responde 'CHAT'. Solo una palabra.

        Mensaje actual: "{user_message}"
        """

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Eres un clasificador de intención ultra-rápido."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=5,
            temperature=0.0,
            timeout=8,
        )
        decision = str(response.choices[0].message.content or "").strip().upper()
        logger.info(f"Scout Decision remoto: {decision} para mensaje: {user_message[:30]}...")
        return "AGENT" in decision

    def should_use_agents(self, user_message: str, history: Optional[list] = None) -> bool:
        try:
            local_decision = self._should_use_agents_local(user_message, history)
            if local_decision is not None:
                return local_decision
            return self._should_use_agents_remote(user_message, history)
        except Exception as e:
            logger.error(f"Error en Scout Orchestrator: {e}")
            return False


scout = ScoutOrchestrator()
