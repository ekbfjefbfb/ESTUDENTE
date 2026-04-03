"""
Chat Schemas - Pydantic models for chat API
Separado de unified_chat_router.py para reducir responsabilidades
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class ChatMessageRequest(BaseModel):
    message: str
    files: Optional[List[str]] = None
    images: Optional[List[str]] = None  # Soporte explícito para imágenes (Base64 o URLs)
    documents: Optional[List[str]] = None # Soporte para documentos adicionales
    session_id: Optional[str] = None
    # True = forzar prefetch Tavily/Serper antes de llamar al modelo
    web_search: bool = False


class RichGalleryItem(BaseModel):
    title: str
    source: Optional[str] = None
    url: str
    image_url: Optional[str] = None
    style: Optional[str] = None


class RichResponse(BaseModel):
    type: str = "rich_response"
    text: str
    memory_id: Optional[str] = None
    gallery: Optional[List[RichGalleryItem]] = None
    suggestions: Optional[List[str]] = None


class ChatResponse(BaseModel):
    success: bool
    response: str
    user_id: str
    timestamp: str
    context: Optional[Dict[str, Any]] = None
    message_id: Optional[str] = None
    actions: Optional[List[Dict[str, Any]]] = None
    sources: Optional[List[Dict[str, Any]]] = None
    rich_response: Optional[RichResponse] = None


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


class STTRequest(BaseModel):
    """Request para Speech-to-Text"""
    language: Optional[str] = "es"


class STTResponse(BaseModel):
    """Response de Speech-to-Text"""
    success: bool
    text: str
    language: str
    duration_ms: Optional[int] = None
    timestamp: str


class TTSRequest(BaseModel):
    """Request para Text-to-Speech"""
    text: str
    voice: Optional[str] = "male_1"
    speed: Optional[float] = 1.0
    language: Optional[str] = "es"


class TTSResponse(BaseModel):
    """Response de Text-to-Speech"""
    success: bool
    audio: str  # base64 data URI
    text: str
    voice: str
    timestamp: str


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    error_code: str
    timestamp: str
