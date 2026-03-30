"""
Image Analysis Router — Endpoints para análisis de imágenes y documentos.

Endpoints:
    POST /api/images/analyze     — Analizar imagen (OCR + descripción IA)
    POST /api/documents/analyze  — Analizar documento (PDF/imagen → texto + resumen)
    GET  /api/images/config      — Configuración para el frontend

Schema para el Frontend:
    - Enviar archivos como multipart/form-data
    - Campo 'file' con la imagen o documento
    - Campos opcionales: language, extract_text, describe, max_tokens
"""

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from utils.auth import get_current_user
from services.image_analysis_service import (
    analyze_image,
    analyze_document,
    FileValidationError,
    ProcessingError,
    MAX_FILE_SIZE_MB,
    SUPPORTED_IMAGE_TYPES,
    SUPPORTED_DOCUMENT_TYPES,
)

logger = logging.getLogger("image_analysis_router")

router = APIRouter(prefix="/api", tags=["Image Analysis"])


# =============================================
# SCHEMAS DE RESPUESTA
# =============================================

class ImageAnalysisResponse(BaseModel):
    """Respuesta de análisis de imagen."""
    success: bool
    extracted_text: Optional[str] = None
    description: Optional[str] = None
    file_info: dict = Field(default_factory=dict)
    processing_time_ms: int = 0
    cache_hit: bool = False


class DocumentAnalysisResponse(BaseModel):
    """Respuesta de análisis de documento."""
    success: bool
    extracted_text: Optional[str] = None
    description: Optional[str] = None
    file_info: dict = Field(default_factory=dict)
    processing_time_ms: int = 0
    cache_hit: bool = False


class UploadConfigResponse(BaseModel):
    """Configuración de subida para el frontend."""
    max_file_size_mb: int
    max_file_size_bytes: int
    supported_image_types: list
    supported_document_types: list
    supported_languages: list
    default_language: str


# =============================================
# ENDPOINTS
# =============================================

@router.post("/images/analyze", response_model=ImageAnalysisResponse)
async def analyze_image_endpoint(
    file: UploadFile = File(..., description="Imagen a analizar"),
    language: str = Form(default="es", description="Idioma de respuesta (es, en)"),
    extract_text: bool = Form(default=True, description="Extraer texto visible (OCR)"),
    describe: bool = Form(default=True, description="Generar descripción"),
    max_tokens: int = Form(default=800, ge=100, le=2000, description="Tokens máximos"),
    current_user=Depends(get_current_user),
):
    """
    📸 Analiza una imagen.
    
    Envía una imagen y obtén:
    - **Texto extraído** (OCR) — todo el texto visible
    - **Descripción** — qué contiene la imagen
    
    **Formato:** multipart/form-data
    
    **Ejemplo con curl:**
    ```bash
    curl -X POST /api/images/analyze \\
      -H "Authorization: Bearer <token>" \\
      -F "file=@foto.jpg" \\
      -F "language=es" \\
      -F "extract_text=true"
    ```
    """
    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "user_id", None)
    
    try:
        # Leer archivo
        file_bytes = await file.read()
        content_type = (file.content_type or "").lower()
        filename = file.filename or "unknown"
        
        # Analizar
        result = await analyze_image(
            file_bytes=file_bytes,
            content_type=content_type,
            filename=filename,
            language=language,
            extract_text=extract_text,
            describe=describe,
            max_tokens=max_tokens,
            user_id=user_id,
        )
        
        return ImageAnalysisResponse(**result)
    
    except FileValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ProcessingError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in image analysis: {e}")
        raise HTTPException(status_code=500, detail="internal_error")


@router.post("/documents/analyze", response_model=DocumentAnalysisResponse)
async def analyze_document_endpoint(
    file: UploadFile = File(..., description="Documento a analizar (PDF o imagen)"),
    language: str = Form(default="es", description="Idioma de respuesta"),
    max_tokens: int = Form(default=1000, ge=100, le=2000, description="Tokens máximos"),
    current_user=Depends(get_current_user),
):
    """
    📄 Analiza un documento completo.
    
    Soporta PDF e imágenes de documentos.
    Retorna texto extraído + resumen estructurado.
    
    **Formato:** multipart/form-data
    
    **Ejemplo con curl:**
    ```bash
    curl -X POST /api/documents/analyze \\
      -H "Authorization: Bearer <token>" \\
      -F "file=@documento.pdf" \\
      -F "language=es"
    ```
    """
    user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "user_id", None)
    
    try:
        file_bytes = await file.read()
        content_type = (file.content_type or "").lower()
        filename = file.filename or "unknown"
        
        result = await analyze_document(
            file_bytes=file_bytes,
            content_type=content_type,
            filename=filename,
            language=language,
            max_tokens=max_tokens,
            user_id=user_id,
        )
        
        return DocumentAnalysisResponse(**result)
    
    except FileValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ProcessingError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in document analysis: {e}")
        raise HTTPException(status_code=500, detail="internal_error")


@router.get("/images/config", response_model=UploadConfigResponse)
async def get_upload_config(current_user=Depends(get_current_user)):
    """
    ⚙️ Configuración de subida para el frontend.
    
    El frontend debe consultar este endpoint para saber:
    - Tipos de archivo soportados
    - Tamaño máximo
    - Idiomas disponibles
    """
    return UploadConfigResponse(
        max_file_size_mb=MAX_FILE_SIZE_MB,
        max_file_size_bytes=MAX_FILE_SIZE_MB * 1024 * 1024,
        supported_image_types=sorted(SUPPORTED_IMAGE_TYPES),
        supported_document_types=sorted(SUPPORTED_DOCUMENT_TYPES),
        supported_languages=["es", "en", "pt", "fr", "de"],
        default_language="es",
    )
