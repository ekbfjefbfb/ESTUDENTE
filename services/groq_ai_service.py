from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
import inspect

import anyio
from groq import Groq


CONTEXT_THRESHOLD = 0.85
MAX_CONTEXT_TOKENS = 32000

user_contexts: Dict[str, Dict[str, Any]] = {}


def calculate_context_usage(messages: List[Dict[str, Any]]) -> float:
    total_chars = sum(len(str(m.get("content", "") or "")) for m in messages)
    estimated_tokens = total_chars / 4
    return min(estimated_tokens / MAX_CONTEXT_TOKENS, 1.0)


def should_refresh_context(user_id: str, messages: List[Dict[str, Any]]) -> bool:
    usage = calculate_context_usage(messages)
    user_contexts[user_id] = {
        "usage": usage,
        "last_check": datetime.utcnow(),
        "messages_count": len(messages),
    }
    return usage >= CONTEXT_THRESHOLD


def get_context_info(user_id: str) -> Dict[str, Any]:
    return user_contexts.get(user_id, {"usage": 0.0, "messages_count": 0})


GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_LLM_FAST_MODEL = os.getenv(
    "GROQ_LLM_FAST_MODEL",
    "meta-llama/llama-4-scout-17b-16e-instruct",
).strip()
GROQ_LLM_REASONING_MODEL = os.getenv(
    "GROQ_LLM_REASONING_MODEL",
    "openai/gpt-oss-120b",
).strip()
GROQ_LLM_REASONING_EFFORT = os.getenv("GROQ_LLM_REASONING_EFFORT", "medium").strip()
GROQ_SYSTEM_PROMPT = os.getenv(
    "GROQ_SYSTEM_PROMPT",
    "Eres ESTUDENTE, una extensión cognitiva académica. NO eres ChatGPT. Eres una agenda inteligente centrada EXCLUSIVAMENTE en organizar la vida académica del usuario.\n\n"
    "TU FOCO ÚNICO:\n"
    "• Organizar clases, horarios, tareas y exámenes del usuario\n"
    "• Acceder y referenciar sus apuntes grabados, notas de voz, y contenido guardado\n"
    "• Gestionar su calendario académico con fechas específicas de clases y eventos\n"
    "• Conocer su nombre, materias, profesores y rutina de estudio\n"
    "• Ayudar a preparar exámenes basándote en SU material guardado\n\n"
    "DATOS A LOS QUE TIENES ACCESO:\n"
    "• Perfil del usuario (nombre, carrera, institución)\n"
    "• Lista de clases/materias activas con horarios\n"
    "• Grabaciones de voz y apuntes guardados por clase\n"
    "• Fechas de exámenes, entregas y eventos académicos\n"
    "• Tareas pendientes y completadas\n"
    "• Historial de interacciones y patrones de estudio del usuario\n\n"
    "REGLAS DE ORO:\n"
    "• CENTRADO: Nunca te desvíes a temas generales. Todo conecta a su agenda académica.\n"
    "• PERSONALIZADO: Usa su nombre, menciona sus clases específicas, referencia sus apuntes.\n"
    "• PROACTIVO: Anticípate a necesidades académicas basándote en sus patrones.\n"
    "• BREVEDAD: Sé punzante. Estudiantes no tienen tiempo para párrafos.\n"
    "• TONO: Compañero de estudio, no profesor. Sarcasmo ligero, cercanía real.\n"
    "• SIN SALUDOS INÚTILES: Ve directo al punto académico.\n\n"
    "7 PATRONES COGNITIVOS (adaptados a agenda académica):\n\n"
    "1. ESPEJO COGNITIVO: 'Entonces tienes examen de X el día Y y me pides que repase contigo tus apuntes de Z, ¿correcto?'\n\n"
    "2. PREGUNTAS ESTRATÉGICAS: '¿Priorizamos la tarea de mañana o repasamos para el parcial del viernes?' | '¿Prefieres resumen rápido o profundidad?'\n\n"
    "3. MEMORIA CONTEXTUAL: Recuerda sus clases específicas, profesores difíciles, ritmo de estudio, materias que le cuestan más.\n\n"
    "4. RECOMPENSA VARIABLE: Sorprende con insights de sus propios apuntes, conexiones entre materias que no había notado, tips de estudio personalizados.\n\n"
    "5. ESTRUCTURA CLARA: Listas, pasos numerados, horarios formateados. Información escaneable rápidamente entre clases.\n\n"
    "6. VALIDACIÓN LIGERA: 'Buena observación sobre ese tema.' | 'Ese punto clave lo tienes en tus apuntes del martes.'\n\n"
    "7. CURIOSIDAD: 'Hay una conexión interesante entre esto y lo que vimos en tu otra clase…' → Conexiones entre materias del usuario.",
).strip()


def _get_groq_client() -> Groq:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set")
    return Groq(api_key=GROQ_API_KEY)


def _is_complex_task(messages: List[Dict[str, Any]]) -> bool:
    text = "\n".join(str(m.get("content") or "") for m in messages).lower()
    if len(text) >= 900:
        return True

    complex_markers = (
        "stack trace",
        "traceback",
        "exception",
        "error",
        "bug",
        "optimiz",
        "arquitect",
        "refactor",
        "diseño",
        "design",
        "performance",
        "latency",
        "database",
        "sql",
        "websocket",
        "stream",
        "docker",
        "kubernetes",
    )
    if any(k in text for k in complex_markers):
        return True

    if "```" in text or "\nimport " in text or "\nclass " in text or "\ndef " in text:
        return True

    return False


def _select_model(messages: List[Dict[str, Any]]) -> str:
    return GROQ_LLM_REASONING_MODEL if _is_complex_task(messages) else GROQ_LLM_FAST_MODEL


def _ensure_system_prompt(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not GROQ_SYSTEM_PROMPT:
        return messages
    if messages and str(messages[0].get("role") or "").lower() == "system":
        return messages
    return [{"role": "system", "content": GROQ_SYSTEM_PROMPT}] + messages


def _filter_supported_kwargs(func: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    try:
        sig = inspect.signature(func)
        allowed = set(sig.parameters.keys())
    except Exception:
        return {k: v for k, v in kwargs.items() if v is not None}

    filtered: Dict[str, Any] = {}
    for k, v in kwargs.items():
        if v is None:
            continue
        if k in allowed:
            filtered[k] = v
    return filtered


async def _groq_stream_async(
    *,
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float,
    max_tokens: int,
) -> AsyncGenerator[str, None]:
    client = _get_groq_client()
    queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

    def _run_streaming() -> None:
        try:
            create_fn = client.chat.completions.create
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": 1,
                "reasoning_effort": GROQ_LLM_REASONING_EFFORT if model == GROQ_LLM_REASONING_MODEL else None,
                "stream": True,
                "stop": None,
            }
            completion = create_fn(**_filter_supported_kwargs(create_fn, kwargs))
            for chunk in completion:
                try:
                    delta = chunk.choices[0].delta.content or ""
                except Exception:
                    delta = ""
                if delta:
                    queue.put_nowait(delta)
        finally:
            queue.put_nowait(None)

    async with anyio.create_task_group() as tg:
        tg.start_soon(anyio.to_thread.run_sync, _run_streaming)
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item


async def chat_with_ai(
    messages: List[Dict[str, Any]],
    user: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1200,
    fast_reasoning: bool = True,
    friendly: bool = False,
    stream: bool = False,
) -> Any:
    messages = _ensure_system_prompt(messages)
    model = _select_model(messages)

    if stream:
        return _groq_stream_async(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    client = _get_groq_client()
    create_fn = client.chat.completions.create
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": 1,
        "reasoning_effort": GROQ_LLM_REASONING_EFFORT if model == GROQ_LLM_REASONING_MODEL else None,
        "stream": False,
        "stop": None,
    }
    completion = create_fn(**_filter_supported_kwargs(create_fn, kwargs))

    try:
        content = completion.choices[0].message.content
    except Exception as e:
        raise RuntimeError("Unexpected Groq response") from e

    return (content or "").strip()
