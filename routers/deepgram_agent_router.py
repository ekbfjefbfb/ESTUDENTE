"""
Deepgram Agent Proxy Router.

Expone una API compatible con OpenAI Chat Completions para que
el Voice Agent de Deepgram o el frontend la usen como Custom LLM Provider.
"""

import json
import time
import uuid
import logging
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from utils.auth import get_current_user_optional, AuthUser
from services.groq_ai_service import _execute_chat_core, _get_user_personal_context
from config import (
    BACKEND_PUBLIC_URL,
    DEEPGRAM_AGENT_OPENAI_PUBLIC_URL,
    DEEPGRAM_AGENT_PUBLIC_URL,
    GROQ_MODEL_FAST,
)

logger = logging.getLogger("deepgram_agent_router")

router = APIRouter(prefix="/api/deepgram", tags=["Deepgram Voice Agent"])


# ==========================================
# 🧩 Modelos de Datos (Pydantic)
# Compatibilidad estricta con OpenAI
# ==========================================

class OpenAI_Message(BaseModel):
    role: str
    content: str

class OpenAIChatRequest(BaseModel):
    model: Optional[str] = GROQ_MODEL_FAST
    messages: List[OpenAI_Message] = Field(..., min_length=1)
    stream: Optional[bool] = False
    temperature: Optional[float] = 0.5
    max_tokens: Optional[int] = 500


# ==========================================
# 🛠️ Utilidades de Streaming (SSE)
# ==========================================

def _format_sse_chunk(request_id: str, content: str, model: str) -> str:
    """Empaqueta un texto parcial en un evento Server-Sent Events (SSE)"""
    chunk = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": content},
                "finish_reason": None
            }
        ]
    }
    return f"data: {json.dumps(chunk)}\n\n"


def _format_sse_done(request_id: str, model: str) -> str:
    """Envía la secuencia final de cierre del stream OpenAI"""
    chunk = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }
        ]
    }
    return f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n"


# ==========================================
# 🔊 Restricciones Sensoriales (Voz Natural)
# ==========================================

VOICE_NATIVE_SYSTEM_PROMPT = """
¡IMPORTANTE! Tu respuesta NO se leerá en una pantalla. Será HABLADA por una voz de sintetización telefónica.
REGLAS ESTRICTAS DE RESPUESTA POR VOZ:
1. NUNCA uses viñetas (*, -, 1., 2.). NUNCA uses Markdown (negritas, cursivas).
2. Habla como un humano natural, fluido y rápido en una llamada.
3. Tus respuestas deben ser CORTAS. Idealmente 1 a 3 oraciones máximo (under 130 caracteres) al menos que te pidan más detalles explícitamente.
4. Usa comas y puntos frecuentemente para hacer que la voz sintetizada haga pausas respiratorias.
5. No des rellenos ("Claro, te explico", "Aquí tienes la respuesta"). Ve directo al grano.
6. No uses emojis ni símbolos decorativos.
"""


# ==========================================
# Endpoints
# ==========================================


def _request_base_url(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}".rstrip("/")
    if BACKEND_PUBLIC_URL:
        return BACKEND_PUBLIC_URL.rstrip("/")
    return str(request.base_url).rstrip("/")


@router.get("/config")
async def deepgram_config(request: Request) -> Dict[str, Any]:
    base_url = _request_base_url(request)
    return {
        "success": True,
        "provider": "deepgram-custom-llm",
        "chat_url": DEEPGRAM_AGENT_PUBLIC_URL or f"{base_url}/api/deepgram/chat",
        "openai_compatible_url": DEEPGRAM_AGENT_OPENAI_PUBLIC_URL or f"{base_url}/api/deepgram/v1/chat/completions",
        "auth_header": "Authorization: Bearer <access_token>",
        "streaming_format": "text/event-stream",
    }


async def _handle_deepgram_chat(
    request: Request,
    payload: OpenAIChatRequest
):
    """
    Endpoint nativo para que Deepgram Voice Agent o el frontend consuman
    el backend como proveedor compatible con OpenAI Chat Completions.
    """
    if not payload.messages:
        raise HTTPException(status_code=400, detail="messages_required")
    # 1. Autenticación (Deepgram manda el Header: Authorization: Bearer <token>)
    auth_header = request.headers.get("Authorization")
    user: Optional[AuthUser] = await get_current_user_optional(auth_header)
    
    # Tolerancia: Si el token falla, seguimos como anónimo, pero advertimos.
    user_id = user.get("user_id") if user else None
    if not user_id:
        logger.warning("Deepgram Voice Agent is querying without a valid user token.")

    # 2. Reconstruir los mensajes
    msgs: List[Dict[str, Any]] = [{"role": m.role, "content": m.content} for m in payload.messages]

    # 3. Inyectar Restricciones de Voz
    msgs.insert(0, {"role": "system", "content": VOICE_NATIVE_SYSTEM_PROMPT})

    # 4. Inyectar Memoria Personal (RAG de Agenda y Notas) de forma desacoplada
    if user_id:
        personal_context = await _get_user_personal_context(user_id)
        if personal_context:
            msgs.insert(1, {
                "role": "system", 
                "content": f"CONTEXTO OBLIGATORIO DEL ESTUDIANTE QUE LLAMA:\n{personal_context}"
            })

    # Variable para el generador
    request_id = f"chatcmpl-{uuid.uuid4().hex}"
    req_model = payload.model or GROQ_MODEL_FAST

    # 5. Si la petición no es Streaming (Raro para agentes Voice, pero posible)
    if not payload.stream:
        # Llamada bloqueante
        final_answer = await _execute_chat_core(
            messages=msgs,
            user=user_id,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            stream=False,
            forced_model=req_model,
            use_web_search=True
        )
        # Formateo JSON plano OpenAI
        return {
            "id": request_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req_model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": final_answer
                },
                "finish_reason": "stop"
            }]
        }

    # 6. Stream Engine (SSE para fluidez <300ms)
    async def sse_stream_generator():
        try:
            # Contactamos al modelo de respuesta ultrarrápida usando nuestro core
            async_generator = await _execute_chat_core(
                messages=msgs,
                user=user_id,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
                stream=True,
                forced_model=req_model,
                use_web_search=True
            )
            
            async for token in async_generator:
                if token:
                    # Empacar cada carácter/palabra a formato OpenAI Delta
                    yield _format_sse_chunk(request_id, token, req_model)
            
            # Cierre elegante de conexión
            yield _format_sse_done(request_id, req_model)
            
        except Exception as e:
            logger.error(f"Error en proxy streaming = {str(e)}")
            error_chunk = _format_sse_chunk(request_id, " Disculpa, tuve un micro corte de memoria.", req_model)
            yield error_chunk
            yield _format_sse_done(request_id, req_model)

    return StreamingResponse(
        sse_stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/chat")
async def deepgram_custom_llm(
    request: Request,
    payload: OpenAIChatRequest
):
    return await _handle_deepgram_chat(request=request, payload=payload)


@router.post("/v1/chat/completions")
async def deepgram_openai_compatible_chat(
    request: Request,
    payload: OpenAIChatRequest
):
    return await _handle_deepgram_chat(request=request, payload=payload)
