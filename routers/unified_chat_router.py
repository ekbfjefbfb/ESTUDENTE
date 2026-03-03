"""
Unified Chat Router Enterprise v5.0
Chat con IA + Voz + Monitoreo de Contexto Automático
"""

from fastapi import APIRouter, WebSocket, UploadFile, File, Depends, HTTPException, Request
from typing import List, Optional
import json
from datetime import datetime

from services.siliconflow_ai_service import chat_with_ai, should_refresh_context, get_context_info
from utils.auth import get_current_user

router = APIRouter(prefix="/unified-chat", tags=["Chat IA"])

@router.post("/message")
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
        
        return {
            "success": True,
            "response": response,
            "user_id": user["user_id"],
            "timestamp": datetime.utcnow().isoformat(),
            "context": {
                "usage_percent": round(context_info.get("usage", 0) * 100, 1),
                "needs_refresh": needs_refresh,
                "auto_refreshed": needs_refresh
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/voice/message")
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
        
        return {
            "success": True,
            "transcribed": text,
            "response": response,
            "audio": audio_response,
            "user_id": user["user_id"],
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/context/{user_id}")
async def get_user_context(user_id: str):
    """Obtener información de contexto del usuario"""
    return get_context_info(user_id)

@router.post("/context/refresh/{user_id}")
async def refresh_user_context(user_id: str):
    """Forzar refresh del contexto del usuario"""
    from services.siliconflow_ai_service import user_contexts
    if user_id in user_contexts:
        del user_contexts[user_id]
    return {"success": True, "message": "Contexto refrescado", "user_id": user_id}

@router.websocket("/ws/{user_id}")
async def unified_chat_websocket(websocket: WebSocket, user_id: str):
    """WebSocket para chat en tiempo real con monitoreo de contexto"""
    
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            messages = [{"role": "user", "content": message_data["message"]}]
            needs_refresh = should_refresh_context(user_id, messages)
            
            response = await chat_with_ai(
                messages=messages,
                user=user_id,
                fast_reasoning=True
            )
            
            await websocket.send_text(json.dumps({
                "response": response,
                "context": {
                    "needs_refresh": needs_refresh,
                    "auto_refreshed": needs_refresh
                }
            }))
            
    except Exception as e:
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": f"Error: {str(e)}"
        }))
        await websocket.close()

__all__ = ["router"]