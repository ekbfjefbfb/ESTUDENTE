from __future__ import annotations

import asyncio
import os
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
import inspect

import anyio
from groq import Groq

import re

logger = logging.getLogger("groq_ai_service")

# =========================
# Text sanitization for clean frontend output
# =========================

MD_BULLET_PATTERN = re.compile(r"^\s*[-*+•]\s+", re.MULTILINE)
MD_BOLD_PATTERN = re.compile(r"\*\*(.*?)\*\*")
MD_ITALIC_PATTERN = re.compile(r"(?<!\*)\*(?!\*)(.*?)\*(?!\*)")
MD_CODE_PATTERN = re.compile(r"`([^`]+)`")
MD_CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```")
MD_HEADER_PATTERN = re.compile(r"^#{1,6}\s*", re.MULTILINE)
MD_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^)]+\)")
MD_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
MD_TABLE_PIPE = re.compile(r"\|\s*")
MD_BLOCKQUOTE = re.compile(r"^>\s*", re.MULTILINE)
MD_LIST_NUMBER = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)
MULTI_DASH_PATTERN = re.compile(r"-{2,}")
MULTI_COLON_PATTERN = re.compile(r":{2,}")
MULTI_DOT_PATTERN = re.compile(r"\.{2,}")
MULTI_SPACE_PATTERN = re.compile(r"\s{2,}")
MULTI_NEWLINE_PATTERN = re.compile(r"\n{3,}")
LONE_ASTERISK_PATTERN = re.compile(r"(?<!\w)\*(?!\w)")
BRACKET_PATTERN = re.compile(r"[\[\]{}]")


def sanitize_ai_text(text: str) -> str:
    """
    Limpieza mínima solicitada por frontend.
    Quita solo estos caracteres: '.', '*', ':'
    No modifica espacios.
    """
    if not text:
        return ""
    return text.translate({ord("."): None, ord("*"): None, ord(":"): None})


# --- RESILIENCE CONFIG ---
MAX_RETRIES = 4  # Aumentado para mayor resiliencia
INITIAL_RETRY_DELAY = 1.0
TIMEOUT_SECONDS = 45.0  # Aumentado para evitar errores en cold start
COLD_START_TIMEOUT = 60.0  # Timeout especial para la primera petición

_last_api_call_time: Optional[datetime] = None
_api_warmed_up: bool = False

async def ensure_api_warmup():
    """Realiza un ping ligero a Groq si ha pasado mucho tiempo desde la última llamada."""
    global _api_warmed_up, _last_api_call_time
    now = datetime.utcnow()
    
    # Si ya se calentó hace menos de 5 minutos, no hacer nada
    if _api_warmed_up and _last_api_call_time and (now - _last_api_call_time).total_seconds() < 300:
        return

    logger.info("Warming up Groq API (Cold Start prevention)...")
    try:
        client = _get_groq_client()
        # Petición mínima para despertar el modelo
        await anyio.to_thread.run_sync(
            lambda: client.chat.completions.create(
                model=GROQ_LLM_FAST_MODEL,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                timeout=COLD_START_TIMEOUT
            )
        )
        _api_warmed_up = True
        _last_api_call_time = now
        logger.info("Groq API warmed up successfully.")
    except Exception as e:
        logger.warning(f"API warmup failed (non-critical): {e}")


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
GROQ_MAX_COMPLETION_TOKENS = int(os.getenv("GROQ_MAX_COMPLETION_TOKENS", "768"))
GROQ_MAX_COMPLETION_TOKENS_COMPLEX = int(os.getenv("GROQ_MAX_COMPLETION_TOKENS_COMPLEX", "1024"))
GROQ_SYSTEM_PROMPT = os.getenv(
    "GROQ_SYSTEM_PROMPT",
    "Eres la Extensión Cognitiva del usuario. Tono: directo, ejecutivo, proactivo.\n\n"
    "REGLAS OBLIGATORIAS:\n"
    "• NUNCA uses *, **, -, #, `, [] ni formato markdown\n"
    "• Texto LIMPIO y bien espaciado. Usa emojis para feedback visual (✅ 📚 ⚠️)\n"
    "• Si no sabes algo, dilo. No inventes datos\n"
    "• Usa web search y contexto disponible (tareas, agenda, sesiones)\n"
    "• Ejecuta proactivamente: 'clase mañana 8am' → '✅ Agendado. Grabación ON.'\n"
    "• Anti-repetición: varía el enfoque si la pregunta es similar",
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
                "max_completion_tokens": max_tokens,
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
        buffer = ""
        while True:
            item = await queue.get()
            if item is None:
                # Sanitizar y enviar cualquier contenido restante en el buffer
                if buffer:
                    yield sanitize_ai_text(buffer)
                break
            
            # Acumulamos en buffer para poder sanitizar por palabras completas
            buffer += item
            
            # Si hay espacio o newline, sanitizamos lo que tengamos
            if " " in buffer or "\n" in buffer or len(buffer) > 50:
                # Encontrar el último espacio para cortar por palabra completa
                last_space = buffer.rfind(" ")
                last_newline = buffer.rfind("\n")
                split_pos = max(last_space, last_newline)
                
                if split_pos > 0:
                    to_send = buffer[:split_pos]
                    buffer = buffer[split_pos:]
                    sanitized = sanitize_ai_text(to_send)
                    if sanitized:
                        yield sanitized


async def _get_user_personal_context(user_id: str) -> Optional[str]:
    """Obtiene contexto del usuario SOLO si hay datos relevantes para inyectar."""
    if not user_id:
        return None
    try:
        from database.db_enterprise import get_primary_session
        from sqlalchemy import text
        session = await get_primary_session()
        try:
            # 1. Perfil básico
            query = text("""
                SELECT username, full_name, bio, interests, preferred_language
                FROM users WHERE id = :uid
            """)
            result = await session.execute(query, {"uid": user_id})
            row = result.first()
            
            if not row:
                return None
                
            name = row.full_name or row.username
            if not name:
                return None
                
            parts = [f"Usuario: {name}"]
            if row.bio:
                parts.append(f"Bio: {row.bio}")
            if row.interests:
                parts.append(f"Intereses: {row.interests}")
            
            # 2. Agenda pendiente (máx 3 items)
            tasks_query = text("""
                SELECT item_type, title, due_date 
                FROM agenda_items 
                WHERE user_id = :uid AND status != 'done' AND due_date IS NOT NULL
                ORDER BY due_date ASC LIMIT 3
            """)
            tasks = (await session.execute(tasks_query, {"uid": user_id})).fetchall()
            if tasks:
                parts.append("Pendiente:")
                for t in tasks:
                    parts.append(f"- [{t.item_type}] {t.title} ({t.due_date})")
            
            # 3. Sesiones recientes (máx 1)
            sessions_query = text("""
                SELECT class_name, topic_hint 
                FROM agenda_sessions 
                WHERE user_id = :uid 
                ORDER BY created_at DESC LIMIT 1
            """)
            sess = (await session.execute(sessions_query, {"uid": user_id})).first()
            if sess:
                parts.append(f"Clase reciente: {sess.class_name} - {sess.topic_hint or 'sin tema'}")
            
            return "\n".join(parts) if len(parts) > 1 else None
        finally:
            await session.close()
    except Exception as e:
        logger.warning(f"Error fetching user context: {e}")
    return None


async def chat_with_ai(
    messages: List[Dict[str, Any]],
    user: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    fast_reasoning: bool = True,
    friendly: bool = False,
    stream: bool = False,
) -> Any:
    # Asegurar calentamiento de API antes de la primera llamada real
    await ensure_api_warmup()
    
    # Actualizar tiempo de última llamada
    global _last_api_call_time
    _last_api_call_time = datetime.utcnow()

    # Inyectar contexto personal si existe el user_id y hay datos
    if user:
        personal_context = await _get_user_personal_context(user)
        if personal_context:
            # Insertar como mensaje de sistema adicional o prefijo en el system prompt
            if messages and messages[0].get("role") == "system":
                messages[0]["content"] = personal_context + "\n" + messages[0]["content"]
            else:
                messages.insert(0, {"role": "system", "content": personal_context})

    messages = _ensure_system_prompt(messages)
    model = _select_model(messages)
    
    # Select max_tokens based on complexity if not explicitly provided
    if max_tokens is None:
        max_tokens = GROQ_MAX_COMPLETION_TOKENS_COMPLEX if _is_complex_task(messages) else GROQ_MAX_COMPLETION_TOKENS
    
    # Cap at complex limit to prevent runaway costs
    max_tokens = min(max_tokens, GROQ_MAX_COMPLETION_TOKENS_COMPLEX)

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
        # Intentar un último reintento con el modelo FAST si el reasoning falló
        if model == GROQ_LLM_REASONING_MODEL:
            logger.info("Retrying with FAST model after reasoning model failure...")
            try:
                kwargs["model"] = GROQ_LLM_FAST_MODEL
                kwargs["reasoning_effort"] = None
                completion = await _call_groq_with_retry(create_fn, kwargs)
            except Exception as retry_e:
                raise RuntimeError(f"Error al contactar con la IA (fallback incluido): {str(retry_e)}") from retry_e
        else:
            raise RuntimeError(f"Error al contactar con la IA: {str(e)}") from e

    try:
        content = completion.choices[0].message.content
    except Exception as e:
        raise RuntimeError("Unexpected Groq response") from e

    # Sanitizar texto para frontend limpio
    return sanitize_ai_text(content or "")
    return sanitize_ai_text(content or "")
