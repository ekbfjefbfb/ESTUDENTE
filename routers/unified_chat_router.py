"""
Unified Chat Router Enterprise v5.0
Chat con IA + Voz + Monitoreo de Contexto Automático
Diseñado para integración óptima con frontend
"""

from fastapi import APIRouter, WebSocket, UploadFile, File, Depends, HTTPException, Request
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import json
from datetime import datetime

from services.siliconflow_ai_service import chat_with_ai, should_refresh_context, get_context_info
from utils.auth import get_current_user

router = APIRouter(prefix="/unified-chat", tags=["Chat IA"])

# =========================
# SCHEMAS
# =========================

class ChatMessageRequest(BaseModel):
    message: str
    files: Optional[List[str]] = None
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    success: bool
    response: str
    user_id: str
    timestamp: str
    context: Dict[str, Any]
    message_id: Optional[str] = None

class VoiceChatResponse(BaseModel):
    success: bool
    transcribed: str
    response: str
    audio: str
    user_id: str
    timestamp: str
    message_id: Optional[str] = None

class ContextResponse(BaseModel):
    user_id: str
    usage_percent: float
    messages_count: int
    last_check: Optional[str] = None

class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    error_code: str
    timestamp: str

# =========================
# ENDPOINTS
# =========================

@router.post("/message", response_model=ChatResponse)
async def unified_chat_message(
    message: str,
    files: Optional[List[UploadFile]] = File(None),
    user: dict = Depends(get_current_user),
):
    """Chat con IA - auto-monitorea contexto y refresca si es necesario"""
    
    try:
        messages = [{"role": "user", "content": message}]
        
        context_info = get_context_info(user["user_id"])
        needs_refresh = should_refresh_context(user["user_id"], messages)
        
        response = await chat_with_ai(
            messages=messages,
            user=user["user_id"],
            fast_reasoning=True
        )
        
        return ChatResponse(
            success=True,
            response=response,
            user_id=user["user_id"],
            timestamp=datetime.utcnow().isoformat(),
            context={
                "usage_percent": round(context_info.get("usage", 0) * 100, 1),
                "needs_refresh": needs_refresh,
                "auto_refreshed": needs_refresh
            },
            message_id=f"msg_{datetime.utcnow().timestamp()}"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": str(e),
                "error_code": "CHAT_ERROR",
                "timestamp": datetime.utcnow().isoformat()
            }
        )

@router.post("/message/json", response_model=ChatResponse)
async def unified_chat_message_json(
    request: ChatMessageRequest,
    user: dict = Depends(get_current_user),
):
    """Chat con IA - versión JSON body"""
    
    try:
        messages = [{"role": "user", "content": request.message}]
        
        context_info = get_context_info(user["user_id"])
        needs_refresh = should_refresh_context(user["user_id"], messages)
        
        response = await chat_with_ai(
            messages=messages,
            user=user["user_id"],
            fast_reasoning=True
        )
        
        return ChatResponse(
            success=True,
            response=response,
            user_id=user["user_id"],
            timestamp=datetime.utcnow().isoformat(),
            context={
                "usage_percent": round(context_info.get("usage", 0) * 100, 1),
                "needs_refresh": needs_refresh,
                "auto_refreshed": needs_refresh,
                "session_id": request.session_id
            },
            message_id=f"msg_{datetime.utcnow().timestamp()}"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": str(e),
                "error_code": "CHAT_ERROR",
                "timestamp": datetime.utcnow().isoformat()
            }
        )

@router.post("/voice/message", response_model=VoiceChatResponse)
async def chat_with_voice(
    audio: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Chat por voz - STT → Qwen3 → TTS"""
    
    try:
        audio_bytes = await audio.read()
        
        from services.siliconflow_ai_service import transcribe_audio, text_to_speech
        
        text = await transcribe_audio(audio_bytes)
        
        response = await chat_with_ai(
            messages=[{"role": "user", "content": text}],
            user=user["user_id"]
        )
        
        audio_response = await text_to_speech(response)
        
        return VoiceChatResponse(
            success=True,
            transcribed=text,
            response=response,
            audio=audio_response,
            user_id=user["user_id"],
            timestamp=datetime.utcnow().isoformat(),
            message_id=f"voice_{datetime.utcnow().timestamp()}"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": str(e),
                "error_code": "VOICE_CHAT_ERROR",
                "timestamp": datetime.utcnow().isoformat()
            }
        )

@router.get("/context/{user_id}", response_model=ContextResponse)
async def get_user_context(user_id: str):
    """Obtener información de contexto del usuario"""
    info = get_context_info(user_id)
    return ContextResponse(
        user_id=user_id,
        usage_percent=round(info.get("usage", 0) * 100, 1),
        messages_count=info.get("messages_count", 0),
        last_check=info.get("last_check").isoformat() if info.get("last_check") else None
    )

@router.post("/context/refresh/{user_id}")
async def refresh_user_context(user_id: str):
    """Forzar refresh del contexto del usuario"""
    from services.siliconflow_ai_service import user_contexts
    if user_id in user_contexts:
        del user_contexts[user_id]
    return {
        "success": True, 
        "message": "Contexto refrescado", 
        "user_id": user_id,
        "timestamp": datetime.utcnow().isoformat()
    }

@router.get("/health")
async def chat_health():
    """Health check del servicio de chat"""
    return {
        "status": "healthy",
        "service": "unified-chat",
        "version": "5.0",
        "features": ["text", "voice", "websocket", "context_monitoring"],
        "timestamp": datetime.utcnow().isoformat()
    }

@router.get("/info")
async def chat_info():
    """Información del servidor de chat para frontend"""
    return {
        "service": "unified-chat",
        "version": "5.0",
        "model": "Qwen/Qwen3-VL-32B-Instruct",
        "provider": "SiliconFlow",
        "features": {
            "text_chat": True,
            "voice_chat": True,
            "websocket": True,
            "context_monitoring": True,
            "auto_context_refresh": True
        },
        "limits": {
            "max_context_tokens": 32000,
            "context_threshold_percent": 85,
            "max_audio_size_mb": 10
        },
        "timestamp": datetime.utcnow().isoformat()
    }

@router.websocket("/ws/{user_id}")
async def unified_chat_websocket(websocket: WebSocket, user_id: str):
    """WebSocket para chat en tiempo real con monitoreo de contexto"""
    
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            messages = [{"role": "user", "content": message_data.get("message", "")}]
            needs_refresh = should_refresh_context(user_id, messages)
            
            response = await chat_with_ai(
                messages=messages,
                user=user_id,
                fast_reasoning=message_data.get("fast_reasoning", True)
            )
            
            await websocket.send_text(json.dumps({
                "success": True,
                "response": response,
                "message_id": f"ws_{datetime.utcnow().timestamp()}",
                "context": {
                    "needs_refresh": needs_refresh,
                    "auto_refreshed": needs_refresh
                },
                "timestamp": datetime.utcnow().isoformat()
            }))
            
    except json.JSONDecodeError:
        await websocket.send_text(json.dumps({
            "success": False,
            "error": "Invalid JSON",
            "error_code": "INVALID_JSON",
            "timestamp": datetime.utcnow().isoformat()
        }))
        await websocket.close()
    except Exception as e:
        await websocket.send_text(json.dumps({
            "success": False,
            "error": str(e),
            "error_code": "WS_ERROR",
            "timestamp": datetime.utcnow().isoformat()
        }))
        await websocket.close()

__all__ = ["router"]