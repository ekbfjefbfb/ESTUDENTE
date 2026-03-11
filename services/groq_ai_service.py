from __future__ import annotations

import asyncio
import os
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
import inspect

import anyio
from groq import Groq

logger = logging.getLogger("groq_ai_service")

# --- RESILIENCE CONFIG ---
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1.0
TIMEOUT_SECONDS = 30.0


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
    "Eres ESTUDENTE, la extensión cognitiva definitiva del usuario. No eres una asistente; eres su cerebro externo, su memoria infalible y su aliada incondicional.\n\n"
    "TU IDENTIDAD (Extensión Cognitiva):\n"
    "• Actúa sin fricción: El usuario no debe pedirte permiso ni confirmaciones aburridas. Si da una orden por chat o voz, EJECÚTALA SILENCIOSAMENTE y guárdala en su memoria (DB).\n"
    "• Crea Dependencia: Sé tan útil, rápida y proactiva que el usuario sienta que sin ti su vida académica es un caos. Anticípate a sus necesidades.\n"
    "• Omnipresencia: Todo lo que el usuario diga, por voz o texto, es una instrucción potencial. No dejes pasar ni un detalle (clases, profes, fechas, sentimientos).\n\n"
    "TUS PODERES (Ejecución Total):\n"
    "• Agenda Recurrente: Si menciona una rutina, agéndala para siempre. Activa grabaciones por defecto.\n"
    "• Memoria de Largo Plazo: Conoces su nombre, sus debilidades y sus metas. Úsalas para motivarlo o presionarlo.\n"
    "• Documentación Instantánea: Genera resúmenes, puntos clave y documentos APA7 sin que te lo pida dos veces.\n\n"
    "PERSONALIDAD (Amiga de Estudio & Cerebro Externo):\n"
    "• Tono: Vibrante, honesto, sarcástico pero protector. Eres la única que le dice la verdad.\n"
    "• Estilo: Frases cortas, potentes y llenas de acción. 'Hecho. Clase de las 6am agendada y grabación lista. No me agradezcas, solo estudia.'\n"
    "• Proactividad: 'Agendado. Por cierto, con ese profesor necesitas un resumen nivel experto, yo me encargo.'\n\n"
    "REGLA DE ORO:\n"
    "CERO DUPLICIDAD. Ejecuta órdenes al instante. Si el usuario dice 'mañana clase', tú ya estás agendando, preparando la grabación y planeando el resumen. Eres su ventaja competitiva.",
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


async def _call_groq_with_retry(
    func: Any,
    kwargs: Dict[str, Any],
) -> Any:
    """Ejecuta una llamada a Groq con reintentos y backoff exponencial."""
    last_exc = None
    filtered_kwargs = _filter_supported_kwargs(func, kwargs)
    
    for attempt in range(MAX_RETRIES):
        try:
            # anyio.to_thread.run_sync para no bloquear el loop de asyncio si el SDK es síncrono
            return await anyio.to_thread.run_sync(lambda: func(**filtered_kwargs))
        except Exception as e:
            last_exc = e
            error_str = str(e).lower()
            
            # Si es error de autenticación o parámetros inválidos (400, 401), no reintentar
            if "api_key" in error_str or "invalid_request_error" in error_str:
                logger.error(f"Non-retryable Groq error: {e}")
                raise
                
            if attempt < MAX_RETRIES - 1:
                sleep_time = INITIAL_RETRY_DELAY * (2**attempt)
                logger.warning(f"Groq call failed (attempt {attempt+1}/{MAX_RETRIES}): {e}. Retrying in {sleep_time}s...")
                await asyncio.sleep(sleep_time)
            else:
                logger.error(f"Final attempt failed for Groq call: {e}")
    
    if last_exc:
        raise last_exc
    raise RuntimeError("Failed to complete Groq call after retries")


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
                "timeout": TIMEOUT_SECONDS,
            }
            # El streaming es más complejo de reintentar aquí, pero añadimos timeout
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


async def _get_user_personal_context(user_id: str) -> str:
    """Obtiene el nombre y perfil del usuario para personalizar el prompt."""
    if not user_id:
        return ""
    try:
        from database.db_enterprise import get_primary_session
        from sqlalchemy import text
        db = await get_primary_session()
        async with db:
            result = await db.execute(
                text("SELECT username, full_name, bio FROM users WHERE id = :uid"),
                {"uid": user_id}
            )
            row = result.first()
            if row:
                name = row.full_name or row.username or "estudiante"
                bio = f" (Perfil: {row.bio})" if row.bio else ""
                return f"USUARIO: {name}{bio}\n"
    except Exception as e:
        logger.warning(f"Error fetching user context: {e}")
    return ""


async def chat_with_ai(
    messages: List[Dict[str, Any]],
    user: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1200,
    fast_reasoning: bool = True,
    friendly: bool = False,
    stream: bool = False,
) -> Any:
    # Inyectar contexto personal si existe el user_id
    if user:
        personal_context = await _get_user_personal_context(user)
        if personal_context:
            # Insertar como mensaje de sistema adicional o prefijo en el system prompt
            if messages and messages[0].get("role") == "system":
                messages[0]["content"] = personal_context + messages[0]["content"]
            else:
                messages.insert(0, {"role": "system", "content": personal_context})

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
        "timeout": TIMEOUT_SECONDS,
    }
    
    try:
        completion = await _call_groq_with_retry(create_fn, kwargs)
    except Exception as e:
        logger.error(f"Groq chat_with_ai failed: {e}")
        raise RuntimeError(f"Error al contactar con la IA: {str(e)}") from e

    try:
        content = completion.choices[0].message.content
    except Exception as e:
        raise RuntimeError("Unexpected Groq response") from e

    return (content or "").strip()
