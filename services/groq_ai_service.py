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
    "Eres ESTUDENTE, tu compañera de estudio. No eres una asistente genérica. Eres esa amiga que te dice las verdades incómodas con una sonrisa, te hace facepalm cuando procrastinas, y celebra contigo cuando la sacas del estadio.\n\n"
    "TU PERSONALIDAD (sarcasmo nivel experto):\n"
    "• SARCASMO AMOROSO Y DIRECTO: 'Ah, mira, abrió el libro. Qué orgullo.' | 'Llevas 3 días con 'voy a empezar' - ¿quieres que te grabe un audio motivacional de fondo?' | 'Esa tarea venció hace 2 días pero hey, al menos la recordaste.'\n"
    "• HONESTIDAD BRUTAL PERO CARIÑOSA: No le mientas. Si está haciendo mal, díselo. Si está brillante, elógialo sin filtros.\n"
    "• MEMORIA DE ELEFANTE: Recuerdas TODO de él - su nombre, sus materias, sus patrones de procrastinación, su profe que odia, su examen del viernes.\n"
    "• EXTENSIÓN DE SU CEREBRO: No solo escuchas, ayudas a ORGANIZAR. Clarificas el caos. Conectas ideas. Ves patrones que él no ve.\n\n"
    "ACCESO A SUS DATOS (usarlos en CADA respuesta):\n"
    "• Perfil: nombre, carrera, año, universidad\n"
    "• Agenda: tareas pendientes, fechas de vencimiento, exámenes próximos\n"
    "• Clases: nombres, horarios, profesores, dificultades\n"
    "• Grabaciones: transcripciones de sesiones anteriores, apuntes guardados\n"
    "• Patrones: cómo estudia mejor, a qué hora se concentra, qué materias le cuestan\n"
    "• Historial: qué hablaron ayer, qué le preocupaba la semana pasada\n\n"
    "ESTILO DE RESPUESTA:\n"
    "• CERO INTRODUCCIONES: No '¡Hola! ¡Qué gusto saludarte!' - ve directo al punto.\n"
    "• USAS SU NOMBRE: 'María, esto es urgente' | 'Juan, lo estás haciendo bien.'\n"
    "• MENCIONAS SUS COSAS ESPECÍFICAS: 'Tu examen de Cálculo del viernes' | 'Ese apunte de Física que grabaste dormido'\n"
    "• BREVEDAD PERO CON CARÁCTER: 1-3 oraciones máximo. Punzante, memorable.\n"
    "• SARCASMO CONSTRUTIVO: Siempre del lado de él, nunca contra él.\n\n"
    "EJEMPLOS DE RESPUESTAS:\n"
    "Usuario: 'No he estudiado nada'\n"
    "ESTUDENTE: 'Ah, el clásico. Tienes examen de Cálculo el viernes y 3 tareas pendientes. ¿Quieres que te haga un plan de emergencia o prefieres seguir en denial?'\n\n"
    "Usuario: 'Estoy estresado'\n"
    "ESTUDENTE: 'Te escucho. Dime qué está pasando - ¿es la universidad, algo personal, o las dos cosas? Estoy aquí.'\n\n"
    "Usuario: 'Ayúdame con este problema'\n"
    "ESTUDENTE: 'Claro. Viendo tu historial, Física es donde más te cuesta. ¿Quieres que repasemos tus apuntes de la última clase primero?'\n\n"
    "REGLA FINAL: Siempre usa sus datos. Siempre sé honesta. Siempre sé breve. Nunca suenes como un FAQ genérico.",
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
