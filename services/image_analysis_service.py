"""
Image Analysis Service — Procesamiento de imágenes y documentos.

Recibe imágenes/documentos del frontend, los analiza usando:
1. Groq con modelo de visión (si soporta multimodal)
2. Descripción y extracción de texto vía IA
3. Análisis de documentos (PDF, imágenes de texto)

Diseñado para:
- NO bloquear el event loop (usa anyio.to_thread para operaciones pesadas)
- Validar tamaño y tipo antes de procesar (anti-DoS)
- Ser modular y extensible (nuevos providers sin cambiar la interfaz)
"""

import base64
import hashlib
import logging
import time
from typing import Any, Dict, Optional

import anyio

from utils.bounded_dict import BoundedDict

logger = logging.getLogger("image_analysis_service")

# =============================================
# CONFIGURACIÓN
# =============================================
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

SUPPORTED_IMAGE_TYPES = {
    "image/jpeg", "image/jpg", "image/png", "image/webp",
    "image/gif", "image/bmp", "image/tiff",
}

SUPPORTED_DOCUMENT_TYPES = {
    "application/pdf",
    "image/jpeg", "image/jpg", "image/png", "image/webp",
    "image/tiff", "image/bmp",
}

ALL_SUPPORTED_TYPES = SUPPORTED_IMAGE_TYPES | SUPPORTED_DOCUMENT_TYPES

# Cache de resultados recientes (evita re-procesar el mismo archivo)
_result_cache: BoundedDict = BoundedDict(max_size=200, ttl_seconds=1800)


# =============================================
# EXCEPCIONES
# =============================================

class ImageAnalysisError(Exception):
    """Error base para análisis de imágenes."""
    pass


class FileValidationError(ImageAnalysisError):
    """Archivo inválido (tipo, tamaño, etc)."""
    pass


class ProcessingError(ImageAnalysisError):
    """Error durante el procesamiento."""
    pass


# =============================================
# VALIDACIÓN
# =============================================

def validate_file(
    file_bytes: bytes,
    content_type: str,
    filename: str = "",
    max_size_bytes: int = MAX_FILE_SIZE_BYTES,
) -> Dict[str, Any]:
    """
    Valida un archivo antes de procesar.
    
    Returns:
        Dict con metadata del archivo validado
    
    Raises:
        FileValidationError si el archivo no es válido
    """
    # Validar tamaño
    if not file_bytes:
        raise FileValidationError("empty_file")
    
    if len(file_bytes) > max_size_bytes:
        raise FileValidationError(
            f"file_too_large_max_{max_size_bytes // (1024*1024)}mb"
        )
    
    # Normalizar content_type
    content_type = (content_type or "").lower().strip()
    if not content_type or content_type not in ALL_SUPPORTED_TYPES:
        raise FileValidationError(
            f"unsupported_file_type: {content_type}. "
            f"Supported: {', '.join(sorted(ALL_SUPPORTED_TYPES))}"
        )
    
    # Calcular hash para cache/deduplicación
    file_hash = hashlib.sha256(file_bytes).hexdigest()[:16]
    
    return {
        "size_bytes": len(file_bytes),
        "content_type": content_type,
        "filename": filename,
        "file_hash": file_hash,
        "is_image": content_type in SUPPORTED_IMAGE_TYPES,
        "is_pdf": content_type == "application/pdf",
    }


# =============================================
# ANÁLISIS CON GROQ (Visión)
# =============================================

def _build_image_prompt(language: str, extract_text: bool, describe: bool) -> str:
    instructions = []
    if language == "es":
        if describe:
            instructions.append("Describe detalladamente el contenido de esta imagen.")
        if extract_text:
            instructions.append("Extrae TODO el texto visible en la imagen, manteniendo el formato original.")
        instructions.append("Si hay tablas, represéntalas en formato legible.")
        instructions.append("Responde en español.")
    else:
        if describe:
            instructions.append("Describe the content of this image in detail.")
        if extract_text:
            instructions.append("Extract ALL visible text from the image, preserving original formatting.")
        instructions.append("If there are tables, represent them in a readable format.")
    return "\n".join(instructions)


async def _extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extrae texto de un PDF usando reportlab/pdfplumber o similar."""
    try:
        # Intentar con pdfplumber primero (mejor para tablas)
        import pdfplumber
        import io
        
        def _extract():
            text_parts = []
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages[:20]:  # Límite: 20 páginas
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            return "\n\n".join(text_parts)
        
        return await anyio.to_thread.run_sync(_extract)
    except ImportError:
        logger.warning("pdfplumber not installed, trying basic extraction")
    except Exception as e:
        logger.warning(f"PDF extraction failed: {e}")
    
    return ""


# =============================================
# API PÚBLICA
# =============================================

async def analyze_image(
    file_bytes: bytes,
    content_type: str,
    filename: str = "",
    language: str = "es",
    extract_text: bool = True,
    describe: bool = True,
    max_tokens: int = 800,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analiza una imagen y retorna descripción + texto extraído.
    
    Args:
        file_bytes: Bytes del archivo
        content_type: MIME type (image/jpeg, image/png, etc)
        filename: Nombre original del archivo
        language: Idioma de respuesta (es, en)
        extract_text: Si extraer texto (OCR)
        describe: Si generar descripción
        max_tokens: Tokens máximos de respuesta
        user_id: ID del usuario (para tracking)
    
    Returns:
        Dict con campos:
        - success: bool
        - extracted_text: str (si extract_text=True)
        - description: str (si describe=True)
        - file_info: dict con metadata del archivo
        - processing_time_ms: int
    
    Raises:
        FileValidationError: Si el archivo no es válido
        ProcessingError: Si falla el procesamiento
    """
    t0 = time.monotonic()
    
    # 1. Validar archivo
    file_info = validate_file(file_bytes, content_type, filename)
    
    # 2. Verificar cache
    cache_key = f"{file_info['file_hash']}:{language}:{extract_text}:{describe}"
    cached = _result_cache.get(cache_key)
    if cached:
        cached["cache_hit"] = True
        cached["processing_time_ms"] = int((time.monotonic() - t0) * 1000)
        return cached
    
    # 3. Procesar según tipo
    result: Dict[str, Any] = {
        "success": False,
        "file_info": file_info,
    }
    
    try:
        if file_info["is_pdf"]:
            # Para PDFs: extraer texto directo + opcionalmente analizar con IA
            pdf_text = await _extract_text_from_pdf(file_bytes)
            result["extracted_text"] = pdf_text
            
            if describe and pdf_text:
                # Resumir el PDF con IA
                from services.groq_ai_service import chat_with_ai
                summary = await chat_with_ai(
                    messages=[{
                        "role": "user",
                        "content": f"Resume este documento de forma clara y estructurada:\n\n{pdf_text[:3000]}"
                    }],
                    user=user_id,
                    max_tokens=max_tokens,
                )
                result["description"] = summary
            
            result["success"] = True
        
        elif file_info["is_image"]:
            # Para imágenes: formatear y delegar directo al servicio base
            from services.groq_ai_service import chat_with_ai_vision
            from config import GROQ_MODEL_VISION
            
            prompt = _build_image_prompt(language, extract_text, describe)
            b64_image = base64.b64encode(file_bytes).decode("utf-8")
            mime = content_type if content_type else "image/jpeg"
            
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{b64_image}"
                            }
                        }
                    ]
                }
            ]
            
            response_text = await chat_with_ai_vision(
                messages=messages,
                user=user_id,
                temperature=0.1,  # Bajo para mayor precisión en OCR
                max_tokens=max_tokens,
            )
            
            result["raw_response"] = response_text
            result["model_used"] = GROQ_MODEL_VISION
            
            if extract_text and describe:
                result["description"] = response_text
                result["extracted_text"] = response_text
            elif extract_text:
                result["extracted_text"] = response_text
            elif describe:
                result["description"] = response_text
                
            result["success"] = True
        
        else:
            raise FileValidationError(f"unsupported_type: {content_type}")
    
    except (FileValidationError, ProcessingError):
        raise
    except Exception as e:
        logger.error(f"Image analysis failed: {e}")
        raise ProcessingError(f"analysis_failed: {str(e)}")
    
    # 4. Timing y cache
    result["processing_time_ms"] = int((time.monotonic() - t0) * 1000)
    result["cache_hit"] = False
    
    if result["success"]:
        _result_cache[cache_key] = result
    
    logger.info({
        "event": "image_analyzed",
        "user_id": user_id,
        "content_type": content_type,
        "size_bytes": file_info["size_bytes"],
        "processing_time_ms": result["processing_time_ms"],
        "success": result["success"],
    })
    
    return result


async def analyze_document(
    file_bytes: bytes,
    content_type: str,
    filename: str = "",
    language: str = "es",
    max_tokens: int = 1000,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analiza un documento (PDF o imagen de documento).
    Extrae texto + genera resumen estructurado.
    
    Wrapper de conveniencia sobre analyze_image() con defaults de documento.
    """
    return await analyze_image(
        file_bytes=file_bytes,
        content_type=content_type,
        filename=filename,
        language=language,
        extract_text=True,
        describe=True,
        max_tokens=max_tokens,
        user_id=user_id,
    )
