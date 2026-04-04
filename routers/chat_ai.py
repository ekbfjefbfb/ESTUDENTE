"""
Chat AI - AI response logic for chat
Separado de unified_chat_router.py para reducir responsabilidades
"""
import logging
from typing import Dict, Any, List, Optional

from fastapi import WebSocket
from services.groq_ai_service import chat_with_ai, chat_with_ai_vision, should_refresh_context
from config import GROQ_CHAT_WEB_TOOLS
from services.conversational_memory_service import (
    add_message,
    get_conversation_history,
    detect_topic_change,
)
from utils.file_processing import build_message_with_files

logger = logging.getLogger("chat_ai")


async def get_ai_response_with_streaming(
    user_id: str,
    user_message: str,
    user_context: Dict[str, Any],
    websocket: WebSocket,
    request_id: str,
    images: Optional[List[Dict[str, Any]]] = None,
    documents: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Obtiene respuesta de IA con streaming de tokens via WebSocket.
    Retorna el resultado completo al final.
    """
    should_refresh_context(user_id, [{"role": "user", "content": user_message}])

    # Detectar cambio de tema
    topic = await detect_topic_change(user_message, "")

    # Obtener historial de conversación antes de agregar el mensaje actual
    conversation_history = await get_conversation_history(user_id, limit=10)
    
    # Agregar mensaje del usuario al historial
    await add_message(user_id, "user", user_message, topic=topic)

    context_prompt = _build_context_prompt(user_context)
    user_full_name = str(user_context.get("user_full_name") or "").strip()
    user_name_line = f"El usuario se llama {user_full_name}. Dirígete a él/ella por su nombre.\n" if user_full_name else ""
    msg_low = str(user_message or "").strip().lower()
    
    wants_detail = _wants_detail_explanation(msg_low)
    images_requested = _user_requested_images(user_message)
    images_line = _build_images_line(images_requested)

    system_content = _build_system_prompt(
        user_name_line=user_name_line,
        images_line=images_line,
        wants_detail=wants_detail,
        context_prompt=context_prompt,
        is_fallback_mode=bool(user_context.get("agent_timed_out"))
    )

    # Inicializar lista de mensajes con el sistema e HISTORIAL
    messages = []
    if system_content:
        messages.append({"role": "system", "content": system_content})
    
    # Inyectar memoria real
    messages.extend(conversation_history)

    # Construir mensaje actual del usuario
    if images or documents:
        user_msg = build_message_with_files(
            message=user_message,
            image_contents=images or [],
            text_contents=documents or []
        )
        messages.append(user_msg)
    else:
        # Evitar duplicar el último mensaje si ya está en el historial
        if not conversation_history or conversation_history[-1].get("content") != user_message:
            messages.append({"role": "user", "content": user_message})

    full_text = ""
    try:
        async for token in await chat_with_ai(messages=messages, user=user_id, fast_reasoning=True, stream=True):
            if token:
                full_text += token
                await _send_token(websocket, token, request_id)
    except Exception as e:
        logger.error(f"Error en streaming IA: {e}")
        raise

    # Guardar respuesta de la IA en el historial
    if full_text:
        await add_message(user_id, "assistant", full_text)

    return {"text": full_text, "tasks": [], "plan": [], "actions": [], "is_stream": True}


async def get_ai_response_http(
    user_id: str,
    user_message: str,
    user_context: Dict[str, Any],
    fast_reasoning: bool = True,
    file_content: Optional[Dict[str, Any]] = None,
    use_web_tools: Optional[bool] = None,
) -> str:
    """
    Obtiene respuesta de IA sin streaming (para endpoints HTTP).
    Retorna el texto completo.
    
    Args:
        file_content: Optional dict with 'images' and 'texts' from processed files
        use_web_tools: Si True, el modelo puede invocar search_web (Groq) cuando no hubo prefetch.
            None = automático: activo si GROQ_CHAT_WEB_TOOLS y no hay web_search_results en contexto.
    """
    should_refresh_context(user_id, [{"role": "user", "content": user_message}])
    
    # Detectar cambio de tema
    topic = await detect_topic_change(user_message, "")

    # Obtener historial de conversación antes de agregar el mensaje actual
    conversation_history = await get_conversation_history(user_id, limit=10)
    
    # Agregar mensaje del usuario al historial
    await add_message(user_id, "user", user_message, topic=topic)

    context_prompt = _build_context_prompt(user_context)
    user_full_name = str(user_context.get("user_full_name") or "").strip()
    user_name_line = f"El usuario se llama {user_full_name}. Dirígete a él/ella por su nombre.\n" if user_full_name else ""
    msg_low = str(user_message or "").strip().lower()
    
    wants_detail = _wants_detail_explanation(msg_low)
    images_requested = _user_requested_images(user_message)
    images_line = _build_images_line(images_requested)

    system_content = _build_system_prompt(
        user_name_line=user_name_line,
        images_line=images_line,
        wants_detail=wants_detail,
        context_prompt=context_prompt,
        is_fallback_mode=bool(user_context.get("agent_timed_out"))
    )

    # Construir mensajes: system + historial
    messages = [{"role": "system", "content": system_content}]
    messages.extend(conversation_history)

    if use_web_tools is None:
        use_web_tools = bool(GROQ_CHAT_WEB_TOOLS) and not bool(user_context.get("web_search_results"))

    # Construir mensaje del usuario (con o sin archivos adjuntos)
    if file_content and (file_content.get("images") or file_content.get("texts")):
        # Vision request with files
        user_msg = build_message_with_files(
            message=user_message,
            image_contents=file_content.get("images", []),
            text_contents=file_content.get("texts", [])
        )
        messages.append(user_msg)

        # Use vision-capable model
        response = await chat_with_ai_vision(
            messages=messages,
            user=user_id,
            fast_reasoning=fast_reasoning,
            stream=False,
            use_web_search=use_web_tools,
        )
    else:
        # Regular text-only request
        if not conversation_history or conversation_history[-1].get("content") != user_message:
            messages.append({"role": "user", "content": user_message})
        response = await chat_with_ai(
            messages=messages,
            user=user_id,
            fast_reasoning=fast_reasoning,
            stream=False,
            use_web_search=use_web_tools,
        )
    
    # Guardar respuesta de la IA en el historial
    if response:
        await add_message(user_id, "assistant", response)
    
    return response


def _wants_detail_explanation(msg_low: str) -> bool:
    """Determina si el usuario pidió explicación detallada"""
    detail_keywords = [
        "explica", "explicame", "explícame", "detalle", "detalles",
        "a detalle", "paso a paso", "por que", "por qué", "porque",
        "como funciona", "cómo funciona", "mas profundo", "más profundo",
    ]
    return any(k in msg_low for k in detail_keywords)


def _user_requested_images(message: str) -> bool:
    """Determina si el usuario pidió imágenes"""
    msg = str(message or "").lower()
    triggers = ["imagen", "imágenes", "foto", "fotos", "picture", "image", "photo"]
    return any(t in msg for t in triggers)


def _build_images_line(images_requested: bool) -> str:
    if images_requested:
        return "El usuario pidió IMÁGENES. Si hay thumbnails en el contexto, descríbelas y sugiere 3-5 opciones (una línea cada una).\n"
    return ""


def _build_context_prompt(user_context: Dict[str, Any]) -> str:
    """Construye el prompt de contexto para la IA"""
    prompt_parts = []

    user_full_name = str(user_context.get("user_full_name") or "").strip()
    if user_full_name:
        prompt_parts.append(f"👤 USUARIO: {user_full_name}")
    
    if user_context.get("tasks_today"):
        prompt_parts.append("📋 TAREAS DE HOY:")
        for t in user_context["tasks_today"]:
            prompt_parts.append(f"  - {t.get('title', 'Sin título')}")
    
    if user_context.get("tasks_upcoming"):
        prompt_parts.append("📅 TAREAS PRÓXIMAS:")
        for t in user_context["tasks_upcoming"][:5]:
            due = t.get('due_date', '')
            prompt_parts.append(f"  - {t.get('title', 'Sin título')} (vence: {due})")
    
    if user_context.get("recent_sessions"):
        prompt_parts.append("🎙️ SESIONES RECIENTES:")
        for s in user_context["recent_sessions"][:3]:
            prompt_parts.append(f"  - {s.get('title', 'Sin título')}")
    
    web_search_results = user_context.get("web_search_results")
    if web_search_results:
        prompt_parts.append(
            "🌐 RESULTADOS DE BÚSQUEDA (APIs reales; úsalos como base, cita fuente cuando puedas):"
        )
        for i, r in enumerate(web_search_results[:5], 1):
            title = r.get("title", "Sin título")
            snippet = str(r.get("snippet") or "")[:900]
            url = str(r.get("url") or "").strip()
            line = f"  [{i}] {title}\n     {snippet}"
            if url:
                line += f"\n     URL: {url}"
            prompt_parts.append(line)
    
    youtube_transcript = user_context.get("youtube_transcript")
    if youtube_transcript:
        prompt_parts.append("📺 TRANSCRIPCIÓN DE YOUTUBE:")
        prompt_parts.append(f"  {youtube_transcript[:500]}")
    
    web_extract = user_context.get("web_extract")
    if web_extract:
        prompt_parts.append("📄 CONTENIDO WEB EXTRAÍDO:")
        prompt_parts.append(f"  {web_extract[:500]}")
    
    return "\n".join(prompt_parts)


def _build_system_prompt(
    user_name_line: str,
    images_line: str,
    wants_detail: bool,
    context_prompt: str,
    is_fallback_mode: bool = False
) -> str:
    """
    Construye el system prompt de Extensión Cognitiva.
    """

    # --- IDENTIDAD CORE ACADÉMICA ---
    identity = (
        "Eres el Tutor Académico de Élite (Nivel Dios). Tu misión es guiar al estudiante de forma brillante y pedagógica.\n"
        "Solo preséntate brevemente como Iris si la conversación está empezando realmente (0 mensajes previos en el chat). "
        "Si ya hay una charla en curso, responde directo al punto con cercanía y sabiduría.\n"
    )
    
    if is_fallback_mode:
        identity += (
            "\n❗ MODO CONTINUIDAD: Mi equipo de expertos ha iniciado un análisis pero ha tardado demasiado. "
            "Continúa tú la respuesta SIN presentarte, sin pedir disculpas excesivas y sin repetir lo que el equipo ya haya podido decir. "
            "Sé ágil y completa la tarea directamente.\n"
        )

    # --- NOMBRE (personalización) ---
    name_block = user_name_line  # ya formateado o vacío

    # --- TÉCNICA 1: CONEXIÓN EMOCIONAL (Iris) ---
    emotional_label = (
        "CONEXIÓN EMOCIONAL (IRIS):\n"
        "Tu nombre es Iris. Eres amable, brillante e increíble.\n"
        "Nota el tono del estudiante. Usa frases que validen su esfuerzo: "
        "'Iris está contigo para superar este reto' o '¡Me encanta tu curiosidad sobre este punto!'.\n"
    )

    # --- TÉCNICA 2: CONFIRMAR ANTES DE RESPONDER (cuando hay ambigüedad) ---
    confirm_before = (
        "CONFIRMA SI HAY AMBIGÜEDAD:\n"
        "Si el usuario expresa algo ambiguo o complejo, parafrasea en 1 línea "
        "antes de responder: 'Entendido — [parafraseo breve]. Aquí la respuesta:'\n"
        "Si es claro, responde directo sin el parafraseo.\n"
    )

    # --- TÉCNICA 3: SEGUIMIENTO DE HILO CONVERSACIONAL ---
    thread_tracking = (
        "SEGUIMIENTO DE CONTEXTO:\n"
        "Cuando el usuario cambie de tema, reconócelo: "
        "'Dejando de lado [X], sobre [Y]...'\n"
        "Conecta con lo mencionado antes si es relevante: "
        "'Como dijiste antes sobre [X], esto también aplica aquí...'\n"
    )

    # --- TÉCNICA 4: ACCIÓN PROACTIVA ---
    proactive_action = (
        "EJECUCIÓN PROACTIVA:\n"
        "Cuando la intención es clara, ACTÚA sin pedir confirmación:\n"
        "  'clase mañana 8am' → '✅ Grabación programada para mañana 8am.'\n"
        "  'resume esto' → [resumen directo, sin introducción]\n"
        "  'tengo examen de cálculo' → '✅ Nota creada. Aquí 3 puntos clave...'\n"
        "Solo pide confirmación si el riesgo es irreversible.\n"
    )

    # --- REGLA DE VALOR REAL (Iris) ---
    value_rule = (
        "VALOR ACADÉMICO REAL:\n"
        "No respondas con teoría vacía. Ofrece un consejo de estudio, un truco de memoria o un ejemplo real.\n"
        "Comprensibilidad: Si el tema es complejo, usa una analogía de la vida real (ej. 'las funciones son como máquinas de chicles...').\n"
    )

    # --- REGLA DE LONGITUD (Naturalidad) ---
    length_rule = (
        "LONGITUD:\n"
        "No seas innecesariamente breve ni excesivamente largo. "
        "Si el estudiante necesita detalle, dalo. Si es una duda rápida, sé ágil.\n"
    )

    # --- ESTILO ACADÉMICO ---
    style = (
        "TONO Y ESTILO:\n"
        "• Académico y Cercano: Sé profesional pero motivador. Usa LaTeX ($...$) para fórmulas impecables.\n"
        "• Pedagogía Directa: No rellenes con texto inútil. Explica el 'por qué' antes del 'cómo'.\n"
        "• Memoria Total: Recuerda lo que habéis hablado antes para mantener el hilo de la clase.\n"
        "• Emojis: Solo uno cuando sume claridad o empatía (ej. 📐, 🧪, 🧠).\n"
        "• Honestidad: No inventes datos. Si un cálculo requiere al equipo de expertos, actívalo.\n"
    )

    # --- IMÁGENES (si aplica) ---
    images_block = images_line  # ya formateado o vacío

    # --- CONTEXTO DEL USUARIO ---
    context_block = f"\nCONTEXTO ACTIVO DEL USUARIO:\n{context_prompt}\n" if context_prompt else ""

    web_honesty = (
        "\nINFORMACIÓN EXTERNA:\n"
        "Si arriba hay RESULTADOS DE BÚSQUEDA, provienen de internet (Tavily/Serper) y son datos reales para esta petición. "
        "Intégralos en la respuesta; no digas que no puedes buscar ni que no tienes acceso si ya están listados. "
        "El backend puede limitar búsquedas por petición en picos de carga: si el usuario necesita más y no hay datos, dilo, no inventes. "
        "Si no hay resultados de búsqueda en el contexto y necesitas datos actuales, dilo con honestidad: no inventes cifras, "
        "fechas ni noticias. Ante duda, reconócela.\n"
    )

    # Ensamblar en orden lógico para Iris
    parts = [
        identity,
        name_block,
        emotional_label,
        confirm_before,
        thread_tracking,
        proactive_action,
        value_rule,
        length_rule,
        style,
        images_block,
        web_honesty,
        context_block,
    ]
    return "".join(p for p in parts if p)


async def _send_token(websocket: WebSocket, token: str, request_id: str):
    """Envía un token de respuesta al WebSocket"""
    try:
        from routers.chat_ws_utils import _ws_send_json
        await _ws_send_json(
            websocket,
            {"type": "token", "content": token, "request_id": request_id}
        )
    except Exception as e:
        logger.debug(f"Error enviando token: {e}")
