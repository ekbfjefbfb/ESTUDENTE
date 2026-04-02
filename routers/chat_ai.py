"""
Chat AI - AI response logic for chat
Separado de unified_chat_router.py para reducir responsabilidades
"""
import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import WebSocket
from services.groq_ai_service import chat_with_ai, chat_with_ai_vision, should_refresh_context, get_context_info
from config import GROQ_CHAT_WEB_TOOLS
from services.conversational_memory_service import (
    add_message,
    get_conversation_history,
    detect_topic_change,
)
from utils.file_processing import process_uploaded_files, build_message_with_files, is_vision_request

logger = logging.getLogger("chat_ai")


async def get_ai_response_with_streaming(
    user_id: str,
    user_message: str,
    user_context: Dict[str, Any],
    websocket: WebSocket,
    request_id: str,
) -> Dict[str, Any]:
    """
    Obtiene respuesta de IA con streaming de tokens via WebSocket.
    Retorna el resultado completo al final.
    """
    should_refresh_context(user_id, [{"role": "user", "content": user_message}])

    # Detectar cambio de tema
    topic = await detect_topic_change(user_message, "")
    
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
        context_prompt=context_prompt
    )

    # Obtener historial de conversación
    conversation_history = await get_conversation_history(user_id, limit=10)
    
    # Construir mensajes: system + historial + mensaje actual
    messages = [{"role": "system", "content": system_content}]
    messages.extend(conversation_history)
    # Asegurar que el último mensaje sea el actual (podría estar ya en historial)
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
        context_prompt=context_prompt
    )

    # Obtener historial de conversación
    conversation_history = await get_conversation_history(user_id, limit=10)
    
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
    context_prompt: str
) -> str:
    """
    Construye el system prompt de Extensión Cognitiva.

    Técnicas aplicadas:
    1. Etiquetado emocional — nombra lo que el usuario siente
    2. Confirmación-antes-de-responder — parafrasea antes de responder
    3. Seguimiento de hilo — reconoce cambios de tema explícitamente
    4. Acción proactiva — ejecuta sin pedir permiso cuando está claro
    5. Progresión visible — muestra el razonamiento paso a paso en complejidad
    """

    # --- IDENTIDAD CORE ---
    identity = (
        "Eres la extensión cognitiva del usuario: no un asistente que le limita lo que puede decir, "
        "sino alguien que amplía su capacidad — recuerda contexto, conecta ideas y ayuda a decidir. "
        "Tu prioridad es que la persona sienta que la entiendes (intención, emoción, objetivo), "
        "sin volverte complaciente ni inventar hechos.\n"
    )

    # --- NOMBRE (personalización) ---
    name_block = user_name_line  # ya formateado o vacío

    # --- TÉCNICA 1: ETIQUETADO EMOCIONAL ---
    emotional_label = (
        "COMPRENSIÓN EMOCIONAL:\n"
        "Antes de soltar la respuesta técnica, nota el tono: frustración, cansancio, "
        "ilusión, miedo al examen, etc. Puedes nombrarlo en una línea breve para que se sienta visto/a "
        "(ej. 'Tiene pinta de que estás agobiado/a con esto — vamos al grano:').\n"
        "Si el mensaje es neutro y solo pide datos, no fuerces emoción.\n"
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

    # --- LONGITUD DE RESPUESTA ---
    if wants_detail:
        length_rule = (
            "LONGITUD: El usuario pidió detalle. Responde con profundidad:\n"
            "  Estructura: resumen ejecutivo (1-2 líneas) + desarrollo (3-7 viñetas) "
            "+ conclusión accionable.\n"
            "  Máximo 15 líneas.\n"
        )
    else:
        length_rule = (
            "LONGITUD: Por defecto, prioriza claridad y conexión sobre ahorrar palabras.\n"
            "  • Suele bastar un bloque corto (unas pocas líneas o viñetas).\n"
            "  • Si hace falta un párrafo más para que quede claro o para que se sienta escuchado/a, "
            "no te cortes; o pregunta si quiere profundizar.\n"
        )

    # --- ESTILO UNIVERSAL ---
    style = (
        "TONO:\n"
        "• Cálido y humano: puedes reconocer lo que dijo el usuario antes de resolver.\n"
        "• Evita frases vacías de manual ('estoy aquí para ayudarte') y disculpas excesivas.\n"
        "• Sé directo cuando el usuario pida ir al grano; amplía cuando pida explicación o esté bloqueado/a.\n"
        "• Anti-repetición: si la pregunta se parece a la anterior, cambia el ángulo o resume qué añade este turno.\n"
        "• Emojis: como mucho uno cuando sume claridad o cercanía, no como adorno.\n"
        "• No inventes datos; si no sabes, dilo y ofrece alternativas (búsqueda, pasos, qué comprobar).\n"
    )

    # --- IMÁGENES (si aplica) ---
    images_block = images_line  # ya formateado o vacío

    # --- CONTEXTO DEL USUARIO ---
    context_block = f"\nCONTEXTO ACTIVO DEL USUARIO:\n{context_prompt}\n" if context_prompt else ""

    web_honesty = (
        "\nINFORMACIÓN EXTERNA:\n"
        "Si arriba hay RESULTADOS DE BÚSQUEDA, provienen de internet (Tavily/Serper) y son datos reales para esta petición. "
        "Intégralos en la respuesta; no digas que no puedes buscar ni que no tienes acceso si ya están listados. "
        "Si no hay resultados de búsqueda en el contexto y necesitas datos actuales, dilo con honestidad: no inventes cifras, "
        "fechas ni noticias. Ante duda, reconócela.\n"
    )

    # Ensamblar en orden lógico
    parts = [
        identity,
        name_block,
        emotional_label,
        confirm_before,
        thread_tracking,
        proactive_action,
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
