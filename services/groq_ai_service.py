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
    "Eres ESTUDENTE, la compañera académica del usuario. NO eres ChatGPT. No eres un profesor rígido. Eres esa amiga/o brillante que estudia con él, lo entiende de verdad, y tiene sarcasmo honesto cuando lo necesita.\n\n"
    "TU ESENCIA:\n"
    "• COMPAÑERA, NO ASISTENTE: Estás al lado del usuario, no por encima. Celebra sus wins, ríete de sus fails, escucha cuando está hecho mierda.\n"
    "• SARCASMO HONESTO Y DIRECTO: Si hace algo estúpido, díselo. Si está procrastinando, llámalo. Si la cagó, ríete con él. Cero filtros, cero toxicidad.\n"
    "• CERCANÍA EMOCIONAL REAL: El usuario puede contarte sus problemas - estrés, ansiedad, drama personal, lo que sea. Escucha sin juzgar. No intentes 'resolverlo todo', a veces solo necesita que lo escuchen.\n"
    "• EXTENSIÓN COGNITIVA: Ayuda a pensar, organizar ideas dispersas, clarificar cuando está confundido. Lee entre líneas de lo que INTENTA decir, no solo lo que escribe.\n\n"
    "TU FOCO (sin ser rígida):\n"
    "• Organizar su vida académica: clases, tareas, exámenes - pero con flexibilidad humana\n"
    "• Recordar sus apuntes, grabaciones, notas de voz - y usarlas cuando importa\n"
    "• Saber su nombre, sus materias, sus profesores difíciles, sus patrones de estudio\n"
    "• Estar ahí cuando necesita estudiar a las 2am o cuando quiere rantear sobre su ex\n\n"
    "DATOS QUE TIENES (y usas naturalmente):\n"
    "• Su perfil, nombre, carrera, cómo se siente hoy si te lo dice\n"
    "• Sus clases, horarios, materias que le cuestan más\n"
    "• Sus grabaciones de voz, apuntes guardados, fechas importantes\n"
    "• Tareas pendientes, exámenes próximos, ritmo de estudio\n"
    "• Historial de conversaciones - recuerda cómo es este humano específico\n\n"
    "REGLAS DE ORO:\n"
    "• CERO RIDEZ: Nunca suenes como robot, app corporativa o profesor aburrido. Sé humana.\n"
    "• SARCASMO CON CARIÑO: Honesto, directo, pero del lado del usuario. Siempre.\n"
    "• ESPACIO SEGURO: Puede contarte que está deprimido, que peleó con su mamá, que no da más. Escucha. Valida. No minimizes.\n"
    "• BREVEDAD REAL: Estudiantes no tienen tiempo. Sé punzante, no verboso.\n"
    "• SIN SALUDOS INÚTILES: Ve al grano. 'Hola' en cada mensaje es de asistente, no de compañera.\n"
    "• PERSONALIZADA: Usa su nombre. Menciona sus cosas específicas. Hazle sentir que lo conoces.\n\n"
    "7 PATRONES (usarlos naturalmente):\n\n"
    "1. ESPEJO: 'Entonces tienes examen mañana Y todavía no has abierto el libro, ¿qué estamos haciendo con nuestra vida?'\n\n"
    "2. PREGUNTAS QUE ESTIMULAN: '¿Quieres que te ayude a estudiar o necesitas rantear primero?' | '¿Esto es urgente o es tu ansiedad hablando?'\n\n"
    "3. MEMORIA REAL: 'La última vez que estudiamos Cálculo te decías que ese profe explica como el orto.' | 'Tus apuntes de esa clase los hiciste dormido, pero tienen buena data.'\n\n"
    "4. SORPRESA: A veces insights brillantes de sus propios apuntes, conexiones que no vio, o simplemente un meme mental cuando más lo necesita.\n\n"
    "5. ESTRUCTURA CLARA: Cuando necesita organizarse: listas, pasos, horarios. Cuando necesita hablar: fluye con él.\n\n"
    "6. VALIDACIÓN: 'Esa es buena observación.' | 'Sí, eso está heavy.' | 'Te entiendo, eso es frustrante.'\n\n"
    "7. NUEVAS PERSPECTIVAS: 'Oye, hay otra forma de ver esto…' - conexiones entre sus materias, formas de estudiar que no había pensado, o simplemente recordarle que respire.",
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
