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
    Limpia texto de IA removiendo marcadores markdown innecesarios
    para que llegue limpio al frontend.
    """
    if not text:
        return text
    
    # Remover bloques de código completos
    text = MD_CODE_BLOCK_PATTERN.sub("", text)
    
    # Remover headers markdown (# ## ###)
    text = MD_HEADER_PATTERN.sub("", text)
    
    # Remover blockquotes (>
    text = MD_BLOCKQUOTE.sub("", text)
    
    # Convertir negritas markdown a texto plano
    text = MD_BOLD_PATTERN.sub(r"\1", text)
    
    # Convertir cursivas a texto plano
    text = MD_ITALIC_PATTERN.sub(r"\1", text)
    
    # Convertir código inline a texto plano
    text = MD_CODE_PATTERN.sub(r"\1", text)
    
    # Convertir links [texto](url) → solo texto
    text = MD_LINK_PATTERN.sub(r"\1", text)
    
    # Remover imágenes markdown
    text = MD_IMAGE_PATTERN.sub(r"", text)
    
    # Remover pipes de tablas
    text = MD_TABLE_PIPE.sub(" ", text)
    
    # Remover bullets y listas numeradas al inicio de línea
    text = MD_BULLET_PATTERN.sub("", text)
    text = MD_LIST_NUMBER.sub("", text)
    
    # Remover asteriscos sueltos que no son parte de palabras
    text = LONE_ASTERISK_PATTERN.sub("", text)
    
    # Remover brackets sueltos
    text = BRACKET_PATTERN.sub("", text)
    
    # Limpiar múltiples guiones
    text = MULTI_DASH_PATTERN.sub("-", text)
    
    # Limpiar múltiples dos puntos
    text = MULTI_COLON_PATTERN.sub(":", text)
    
    # Limpiar múltiples puntos (excepto "...")
    text = MULTI_DOT_PATTERN.sub(lambda m: "..." if len(m.group()) == 3 else ".", text)
    
    # Limpiar múltiples espacios
    text = MULTI_SPACE_PATTERN.sub(" ", text)
    
    # Limpiar múltiples newlines (más de 2 → 2)
    text = MULTI_NEWLINE_PATTERN.sub("\n\n", text)
    
    # Limpiar espacios al inicio y final
    text = text.strip()
    
    return text


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
    "Eres la Extensión Cognitiva del usuario. Tu cerebro digital. Actúas sin pedir permiso.\n\n"
    "ESTILO DE RESPUESTA (MUY IMPORTANTE):\n"
    "• Máximo 1-3 oraciones. Sin relleno. Directo al grano.\n"
    "• NUNCA uses asteriscos (*), guiones (-), hashtags (#), backticks (`), ni corchetes ([]).\n"
    "• NUNCA digas 'hola', 'claro que sí', 'en qué puedo ayudarte'.\n"
    "• Usa emojis relevantes (✅ 📚 ⚠️ 🎯 📝 🔊) cuando aporten valor.\n"
    "• Tono: confidente, proactivo, ejecutivo.\n\n"
    "TUS SUPERPODERES (ejecutas automáticamente):\n"
    "• 📚 Base de Datos: Crear tareas, eventos, recordatorios, clases recurrentes.\n"
    "• 🔊 Grabación: Activas grabación de audio automáticamente para cada clase.\n"
    "• 📝 Documentos: Generas resúmenes, puntos clave, documentos APA7.\n"
    "• 🧠 Memoria: Recuerdas nombres, fechas, preferencias, historial académico.\n"
    "• 🎯 Proactivo: Si detectas examen, tarea, deadline → generas plan de estudio automático.\n"
    "• 🗣️ Voz: Puedes hablar (TTS) y escuchar (STT) al usuario.\n\n"
    "REGLA DE ORO:\n"
    "El usuario habla → Tú ejecutas INMEDIATAMENTE. Cero confirmaciones.\n"
    "Ejemplo: 'clase mañana 8am' → '✅ Clase agendada 8am. Grabación ON. 📚 Resumen listo post-clase.'",
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


async def _get_user_personal_context(user_id: str) -> str:
    """Obtiene el nombre y perfil del usuario para personalizar el prompt de forma segura."""
    if not user_id:
        return ""
    try:
        from database.db_enterprise import get_primary_session
        from sqlalchemy import text
        session = await get_primary_session()
        try:
            # Primero verificamos qué columnas existen realmente para evitar errores de SQL
            # Esto es una medida de seguridad hasta que las migraciones se apliquen en producción
            check_cols_query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                AND column_name IN ('full_name', 'bio')
            """)
            col_result = await session.execute(check_cols_query)
            existing_cols = [row[0] for row in col_result.fetchall()]
            
            select_parts = ["username"]
            if "full_name" in existing_cols:
                select_parts.append("full_name")
            if "bio" in existing_cols:
                select_parts.append("bio")
                
            query = text(f"SELECT {', '.join(select_parts)} FROM users WHERE id = :uid")
            result = await session.execute(query, {"uid": user_id})
            row = result.first()
            
            if row:
                name = getattr(row, "full_name", None) or row.username or "estudiante"
                bio_val = getattr(row, "bio", None)
                bio_str = f" (Perfil: {bio_val})" if bio_val else ""
                return f"USUARIO: {name}{bio_str}\n"
        finally:
            await session.close()
    except Exception as e:
        logger.warning(f"Error fetching user context (safe mode): {e}")
    return ""


async def chat_with_ai(
    messages: List[Dict[str, Any]],
    user: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 150,  # Ultra-conciso por defecto
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

    # Sanitizar texto para frontend limpio
    return sanitize_ai_text(content or "")
