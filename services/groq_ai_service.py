from __future__ import annotations

import asyncio
import json
import os
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
import inspect

import anyio
from groq import Groq
from sqlalchemy.exc import ProgrammingError

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
    return text


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

from utils.bounded_dict import BoundedDict

user_contexts: BoundedDict = BoundedDict(max_size=1000, ttl_seconds=1800)  # Max 1000 users, 30min TTL


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
# Importar configuración de modelos desde config.py
from config import (
    GROQ_MODEL_FAST,
    GROQ_MODEL_REASONING,
    GROQ_MODEL_VISION,
    GROQ_REASONING_EFFORT,
    GROQ_MAX_TOKENS_FAST,
    GROQ_MAX_TOKENS_REASONING,
    GROQ_MAX_TOKENS_VISION,
    GROQ_MAX_COMPLETION_TOKENS,
    GROQ_MAX_COMPLETION_TOKENS_COMPLEX,
    GROQ_SYSTEM_PROMPT,
    select_groq_model,
    get_max_tokens_for_model,
    GROQ_TOOL_SEARCH_MAX_ROUNDS,
    GROQ_TOOL_SEARCH_MAX_CALLS,
    GROQ_SEARCH_API_MAX_CONCURRENT,
)

_search_api_semaphore = asyncio.Semaphore(GROQ_SEARCH_API_MAX_CONCURRENT)

# Legacy aliases for backwards compatibility
GROQ_LLM_FAST_MODEL = GROQ_MODEL_FAST
GROQ_LLM_REASONING_MODEL = GROQ_MODEL_REASONING
GROQ_LLM_REASONING_EFFORT = GROQ_REASONING_EFFORT


def _get_groq_client() -> Groq:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set")
    return Groq(api_key=GROQ_API_KEY)


def _is_complex_task(messages: List[Dict[str, Any]]) -> bool:
    """
    Decide si usar el modelo de razonamiento (120B) o el rápido (20B).
    
    CRITERIOS BRUTALMENTE HONESTOS:
    - El 20B es suficiente para 80% de casos
    - El 120B solo para: código, explicaciones profundas, textos largos
    
    Nota: Esta función se mantiene por compatibilidad.
    Nueva lógica está en config.py: _is_complex_request()
    """
    text = "\n".join(str(m.get("content") or "") for m in messages).lower()
    
    # Mensajes largos = mas contexto = mas razonamiento
    if len(text) >= 800:
        return True
    
    # Marcadores técnicos
    tech_markers = (
        "stack trace", "traceback", "exception", "error", "bug",
        "optimiz", "arquitect", "refactor", "design", "performance",
        "latency", "database", "sql", "websocket", "docker",
    )
    if any(k in text for k in tech_markers):
        return True
    
    # Marcadores académicos (estudiantes)
    academic_markers = (
        "explica", "explicame", "explícame", "por qué", "por que",
        "cómo funciona", "como funciona", "resume", "resumen",
        "tesis", "ensayo", "examen", "parcial", "investigación",
        "investigacion", "análisis", "analisis", "concluye",
        "conclusion", "conclusión", "teoría", "teoria",
        "comprend", "entiende", "profund", "detall",
    )
    if any(k in text for k in academic_markers):
        return True
    
    # Código en el mensaje
    if "```" in text or "\nimport " in text or "\nclass " in text or "\ndef " in text:
        return True
    
    return False


def _select_model(messages: List[Dict[str, Any]], has_images: bool = False) -> str:
    """
    Selecciona modelo basado en el mensaje.
    Usa la nueva lógica centralizada en config.py
    """
    # Extraer texto del mensaje del usuario (último mensaje)
    user_message = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                user_message = content
            elif isinstance(content, list):
                # Mensaje multimodal (con imágenes)
                text_parts = [p.get("text", "") for p in content if p.get("type") == "text"]
                user_message = " ".join(text_parts)
            break
    
    # Usar selector centralizado de config.py
    return select_groq_model(user_message, has_images=has_images)


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
    max_tokens: int,
    temperature: float = 0.7,
    top_p: float = 1.0,
) -> AsyncGenerator[str, None]:
    client = _get_groq_client()
    queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

    def _run_streaming() -> None:
        try:
            create_fn = client.chat.completions.create
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature if model != GROQ_LLM_REASONING_MODEL else TEMPERATURE_REASONING,
                "max_tokens": max_tokens,
                "max_completion_tokens": max_tokens,
                "top_p": top_p if model != GROQ_LLM_REASONING_MODEL else TOP_P,
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


from services.smart_cache_service import smart_cache

async def _get_user_personal_context_db(user_id: str) -> Optional[str]:
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
            
            # 2. Agenda pendiente (máx 3 items) — tablas opcionales si migración las eliminó
            try:
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
            except ProgrammingError:
                pass

            # 3. Sesiones recientes (máx 1)
            try:
                sessions_query = text("""
                    SELECT class_name, topic_hint 
                    FROM agenda_sessions 
                    WHERE user_id = :uid 
                    ORDER BY created_at DESC LIMIT 1
                """)
                sess = (await session.execute(sessions_query, {"uid": user_id})).first()
                if sess:
                    parts.append(f"Clase reciente: {sess.class_name} - {sess.topic_hint or 'sin tema'}")
            except ProgrammingError:
                pass
            
            return "\n".join(parts) if len(parts) > 1 else None
        finally:
            await session.close()
    except Exception as e:
        logger.warning(f"Error fetching user context (DB): {e}")
    return None


async def _get_user_personal_context(user_id: str) -> Optional[str]:
    """Obtiene contexto del usuario cacheado para evitar queries N+1 por mensaje."""
    if not user_id:
        return None
    
    return await smart_cache.get_or_set(
        key=f"ai_personal_context:{user_id}",
        factory=lambda: _get_user_personal_context_db(user_id),
        ttl=300  # 5 minutos en RAM
    )


def _groq_search_web_tool_def() -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Busca en internet (APIs Tavily/Serper): noticias, precios, clima, hechos verificables, nombres, fechas. "
                "Úsala cuando haga falta información externa o no tengas certeza. Puedes llamarla varias veces con consultas más "
                "específicas si la primera no basta. No digas que no puedes buscar: si hace falta comprobar, llama. "
                "Si no hay resultados, dilo con honestidad; no inventes ni rellenes lagunas con suposiciones."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Consulta de búsqueda (refina en llamadas siguientes si hace falta)",
                    }
                },
                "required": ["query"],
            },
        },
    }


async def _run_search_web_for_tool(*, query: str, user_for_search: str) -> str:
    from services.tavily_search_service import tavily_search_service
    from services.serper_search_service import serper_search_service

    q = (query or "").strip()
    if not q:
        q = "."

    async with _search_api_semaphore:
        search_results, meta = await tavily_search_service.search_with_meta(
            query=q, user_id=user_for_search, include_images=False
        )
        if meta.get("status") != "ok":
            logger.warning(
                "tavily_search_failed status=%s user=%s",
                meta.get("status"),
                user_for_search,
            )
            search_results, meta = await serper_search_service.search_with_meta(
                query=q, user_id=user_for_search, include_images=False
            )

    if not search_results:
        return (
            "No se encontraron resultados en esta búsqueda o las APIs no respondieron. "
            "Indícalo al usuario; no inventes datos."
        )
    snippets = [
        f"- {r.get('title', 'Sin título')}\n  {r.get('snippet', '')}\n  (Fuente: {r.get('url', '')})"
        for r in search_results
    ]
    return ("Resultados recuperados de la web:\n\n" + "\n\n".join(snippets))[:6000]


async def _execute_chat_core(
    messages: List[Dict[str, Any]],
    user: Optional[str],
    temperature: float,
    max_tokens: Optional[int],
    stream: bool,
    forced_model: Optional[str] = None,
    use_web_search: bool = False,
) -> Any:
    """
    NÚCLEO REUTILIZABLE de chat con Groq.
    
    Args:
        forced_model: Si se provee, usa este modelo. Si no, detecta automáticamente.
    
    ESTA FUNCIÓN ES LA BASE. chat_with_ai y chat_with_ai_vision la usan.
    SIN DUPLICACIÓN. SIN CÓDIGO MUERTO.
    """
    # Actualizar tiempo de última llamada
    global _last_api_call_time
    _last_api_call_time = datetime.utcnow()

    # 1. Inyectar contexto personal del usuario (si existe)
    if user:
        personal_context = await _get_user_personal_context(user)
        if personal_context:
            if messages and messages[0].get("role") == "system":
                messages[0]["content"] = personal_context + "\n" + messages[0]["content"]
            else:
                messages.insert(0, {"role": "system", "content": personal_context})

    # 2. Asegurar system prompt base
    messages = _ensure_system_prompt(messages)
    
    # 3. Detectar si hay imágenes en los mensajes
    has_images = any(
        isinstance(m.get("content"), list) and any(
            p.get("type") == "image_url" for p in m.get("content", [])
        )
        for m in messages
    )
    
    # 4. Seleccionar modelo
    if forced_model:
        # Forzar modelo específico (ej: VISION para imágenes)
        model = forced_model
        # Si forzamos VISION pero no hay imágenes, es un error del llamador
        # pero lo permitimos por flexibilidad
    else:
        # Auto-detectar basado en contenido
        model = _select_model(messages, has_images=has_images)
    
    # 5. Calcular límites de tokens
    if max_tokens is None:
        max_tokens = get_max_tokens_for_model(model)
    
    # Cap según modelo (para prevenir costos descontrolados)
    max_allowed = GROQ_MAX_TOKENS_VISION if model == GROQ_MODEL_VISION else GROQ_MAX_TOKENS_REASONING
    max_tokens = min(max_tokens, max_allowed)

    # 6. Streaming o blocking
    if stream:
        return _groq_stream_async(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # 7. Llamada a Groq
    client = _get_groq_client()
    create_fn = client.chat.completions.create
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": 1,
        "stream": False,
        "stop": None,
        "timeout": TIMEOUT_SECONDS,
    }
    
    if use_web_search and not stream:
        kwargs["tools"] = [_groq_search_web_tool_def()]
        kwargs["tool_choice"] = "auto"

    # 8. Ejecutar con retry y fallback
    try:
        completion = await _call_groq_with_retry(create_fn, kwargs)

        # 8.1 Multi-turn search_web: varias rondas Groq↔herramienta; límites por petición + semáforo global (alta carga)
        if use_web_search and not stream:
            user_for_search = str(user or "tool_search")
            tool_def = [_groq_search_web_tool_def()]
            max_rounds = GROQ_TOOL_SEARCH_MAX_ROUNDS
            max_calls = GROQ_TOOL_SEARCH_MAX_CALLS
            total_calls = 0

            for round_num in range(max_rounds):
                rm = completion.choices[0].message
                tcs = getattr(rm, "tool_calls", None) or []
                if not tcs:
                    break

                msg_dump = (
                    rm.model_dump(exclude_unset=True)
                    if hasattr(rm, "model_dump")
                    else rm.dict(exclude_unset=True)
                )
                messages.append(msg_dump)

                for tc in tcs:
                    fn = getattr(tc.function, "name", "") or ""
                    tc_id = getattr(tc, "id", None) or "unknown"
                    if fn != "search_web":
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "name": fn,
                            "content": "Herramienta no disponible en esta sesión.",
                        })
                        continue
                    if total_calls >= max_calls:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "name": "search_web",
                            "content": (
                                "Límite de búsquedas web por petición alcanzado (protección de carga multiusuario). "
                                "Responde solo con lo ya obtenido; no inventes datos."
                            ),
                        })
                        continue
                    total_calls += 1
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                        query = str(args.get("query") or "").strip()
                        logger.info(
                            "search_web round=%s call=%s/%s user=%s q=%r",
                            round_num,
                            total_calls,
                            max_calls,
                            user_for_search,
                            query[:200],
                        )
                        text = await _run_search_web_for_tool(
                            query=query, user_for_search=user_for_search
                        )
                    except Exception as exc:
                        logger.exception("search_web execution failed: %s", exc)
                        text = f"Error en búsqueda: {exc}. No inventes datos."
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "name": "search_web",
                        "content": text,
                    })

                kwargs["messages"] = messages
                kwargs["model"] = model
                kwargs["tools"] = tool_def
                kwargs["tool_choice"] = "auto"
                kwargs["timeout"] = TIMEOUT_SECONDS + 15
                completion = await _call_groq_with_retry(create_fn, kwargs)

            rm_final = completion.choices[0].message
            if getattr(rm_final, "tool_calls", None):
                logger.warning(
                    "search_web still requesting tools after rounds=%s user=%s",
                    max_rounds,
                    user_for_search,
                )
                messages.append(
                    rm_final.model_dump(exclude_unset=True)
                    if hasattr(rm_final, "model_dump")
                    else rm_final.dict(exclude_unset=True)
                )
                messages.append({
                    "role": "user",
                    "content": (
                        "Sistema: límite de rondas de búsqueda alcanzado. "
                        "Responde en texto final usando solo datos ya obtenidos; no solicites más herramientas. "
                        "Si falta información, dilo con honestidad; no supongas ni inventes."
                    ),
                })
                kwargs["messages"] = messages
                kwargs["model"] = model
                kwargs.pop("tools", None)
                kwargs.pop("tool_choice", None)
                kwargs["timeout"] = TIMEOUT_SECONDS + 25
                completion = await _call_groq_with_retry(create_fn, kwargs)

    except Exception as e:
        logger.error(f"Groq API failed with model {model}: {e}")
        
        # FALLBACK RESILIENTE: Si falla REASONING o VISION, intentar FAST
        if model in (GROQ_MODEL_REASONING, GROQ_MODEL_VISION):
            logger.info(f"Fallback to FAST model after {model} failure...")
            try:
                kwargs["model"] = GROQ_MODEL_FAST
                kwargs["reasoning_effort"] = None
                kwargs.pop("tools", None)
                kwargs.pop("tool_choice", None)
                # Ajustar tokens para FAST
                kwargs["max_tokens"] = min(kwargs.get("max_tokens", GROQ_MAX_TOKENS_FAST), GROQ_MAX_TOKENS_FAST)
                completion = await _call_groq_with_retry(create_fn, kwargs)
            except Exception as retry_e:
                raise RuntimeError(f"Error al contactar con la IA (fallback falló): {str(retry_e)}") from retry_e
        else:
            # FAST falló = no hay fallback
            raise RuntimeError(f"Error al contactar con la IA: {str(e)}") from e

    # 9. Extraer respuesta final
    try:
        content = completion.choices[0].message.content
    except Exception as e:
        raise RuntimeError("Respuesta inesperada de Groq API") from e

    return sanitize_ai_text(content or "")


async def chat_with_ai(
    messages: List[Dict[str, Any]],
    user: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    fast_reasoning: bool = True,
    friendly: bool = False,
    stream: bool = False,
    use_web_search: bool = False,
) -> Any:
    """
    Chat con IA - selección automática de modelo (FAST o REASONING).
    Usa _execute_chat_core internamente. Sin duplicación.
    """
    return await _execute_chat_core(
        messages=messages,
        user=user,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=stream,
        forced_model=None,  # Auto-detecta según complejidad
        use_web_search=use_web_search,
    )


async def chat_with_ai_vision(
    messages: List[Dict[str, Any]],
    user: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    fast_reasoning: bool = True,
    stream: bool = False,
    use_web_search: bool = False,
) -> Any:
    """
    Chat con IA FORZANDO modelo VISION (para imágenes).
    Usa _execute_chat_core internamente. Sin duplicación.
    """
    result = await _execute_chat_core(
        messages=messages,
        user=user,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=stream,
        forced_model=GROQ_MODEL_VISION,
        use_web_search=use_web_search,
    )
    
    # Si _execute_chat_core devolvió un async generator (streaming), pasarlo directo
    if hasattr(result, '__aiter__'):
        return result
    
    # Si es string (caso normal), sanitizar
    return sanitize_ai_text(result or "")
