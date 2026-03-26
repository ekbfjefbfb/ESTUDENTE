"""
Chat AI - AI response logic for chat
Separado de unified_chat_router.py para reducir responsabilidades
"""
import asyncio
import logging
import os
from datetime import datetime
from typing import Dict, Any, List

from fastapi import WebSocket
from services.groq_ai_service import chat_with_ai, should_refresh_context, get_context_info

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

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_message},
    ]

    full_text = ""
    try:
        async for token in await chat_with_ai(messages=messages, user=user_id, fast_reasoning=True, stream=True):
            if token:
                full_text += token
                await _send_token(websocket, token, request_id)
    except Exception as e:
        logger.error(f"Error en streaming IA: {e}")
        raise

    return {"text": full_text, "tasks": [], "plan": [], "actions": [], "is_stream": True}


async def get_ai_response_http(
    user_id: str,
    user_message: str,
    user_context: Dict[str, Any],
    fast_reasoning: bool = True
) -> str:
    """
    Obtiene respuesta de IA sin streaming (para endpoints HTTP).
    Retorna el texto completo.
    """
    should_refresh_context(user_id, [{"role": "user", "content": user_message}])

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

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_message},
    ]

    return await chat_with_ai(messages=messages, user=user_id, fast_reasoning=fast_reasoning, stream=False)


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
        prompt_parts.append("🌐 RESULTADOS DE BÚSQUEDA:")
        for r in web_search_results[:3]:
            title = r.get("title", "Sin título")
            snippet = r.get("snippet", "")
            prompt_parts.append(f"  - {title}: {snippet[:100]}")
    
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
    """Construye el prompt del sistema para la IA"""
    system_parts = [
        "Eres la Extensión Cognitiva del usuario.\n",
    ]
    
    if user_name_line:
        system_parts.append(user_name_line)
    
    if images_line:
        system_parts.append(images_line)
    
    if wants_detail:
        system_parts.append(
            "El usuario pidió explicación: puedes responder con más detalle, pero sé directo (máximo 10-14 líneas).\n"
            "Usa: 1 frase + 3-6 viñetas.\n"
        )
    else:
        system_parts.append(
            "Responde corto por defecto: máximo 2-4 líneas, o 3 viñetas cortas.\n"
        )
    
    system_parts.append(
        "No escribas artículos largos. No repitas la pregunta.\n\n"
        "ESTILO:\n"
        "• Cero saludos innecesarios. Cero relleno.\n"
        "• Acción inmediata: el usuario habla, tú ejecutas.\n"
        "• Usa emojis solo si son 1 y aportan valor.\n"
        "• Tono: confidente, proactivo, sin disculpas.\n"
    )
    
    if context_prompt:
        system_parts.append(f"\nCONTEXTO DEL USUARIO:\n{context_prompt}")
    
    return "".join(system_parts)


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
