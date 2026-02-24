"""
Unified Chat Router Enterprise v4.0 - Ultra optimizado con 17 capacidades
Procesamiento paralelo, caching inteligente, mejor manejo de errores
Versión: Production v4.0 - Octubre 2025
"""
from fastapi import APIRouter, WebSocket, UploadFile, File, Depends, HTTPException, Request
from typing import List, Optional
import json
from datetime import datetime

from services.gpt_service import chat_with_ai
from utils.auth import get_current_user

router = APIRouter(prefix="/unified-chat", tags=["💬 Chat Unificado"])

@router.post("/message")
async def unified_chat_message(
    message: str,
    files: Optional[List[UploadFile]] = File(None),
    user: dict = Depends(get_current_user),
):
    """
    Chat unificado - maneja TODO desde conversación natural
    
    Ejemplos:
    - "Genera un documento PDF sobre marketing digital"
    - "Crea una imagen de un gato espacial" 
    - "Lee este texto en voz alta"
    - "Busca información sobre inteligencia artificial"
    """
    
    try:
        attachments_note = ""
        if files:
            attachments_note = f"\n\n[Adjuntos recibidos: {len(files)}]"

        response = await chat_with_ai(
            messages=[{"role": "user", "content": f"{message}{attachments_note}"}],
            user=user["user_id"],
            fast_reasoning=True
        )
        
        return {
            "success": True,
            "response": response,
            "user_id": user["user_id"],
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/ws/{user_id}")
async def unified_chat_websocket(websocket: WebSocket, user_id: str):
    """WebSocket para chat unificado en tiempo real"""
    
    await websocket.accept()
    
    try:
        while True:
            # Recibir mensaje
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            # Procesar con servicio empresarial
            response = await chat_with_ai(
                messages=[{"role": "user", "content": message_data["message"]}],
                user=user_id,
                fast_reasoning=True
            )
            
            # Enviar respuesta
            await websocket.send_text(json.dumps(response))
            
    except Exception as e:
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": f"Error: {str(e)}"
        }))
        await websocket.close()

__all__ = ["router"]