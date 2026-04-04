"""
Master Chat Utils - Parameter extraction utilities
Separado de master_chat_service.py para reducir responsabilidades
"""
import re
import logging
from typing import Dict

logger = logging.getLogger("master_chat_utils")


def extract_image_prompt(message: str) -> str:
    """Extrae prompt de imagen del mensaje"""
    prompt = re.sub(r'(crea|genera|haz|dibuja)\s+(una\s+)?imagen\s+(de\s+)?', '', message, flags=re.IGNORECASE)
    return prompt.strip() or "imagen artística"


def extract_document_topic(message: str) -> str:
    """Extrae tema de documento del mensaje"""
    topic = re.sub(r'(crea|genera|haz)\s+(un\s+)?(pdf|documento)\s+(de\s+|del\s+|sobre\s+)?', '', message, flags=re.IGNORECASE)
    return topic.strip() or "documento informativo"


def extract_text_for_speech(message: str) -> str:
    """Extrae texto para convertir a voz"""
    text = re.sub(r'(convierte|lee|text to speech)\s+(esto\s+|este\s+texto\s*)?:?\s*', '', message, flags=re.IGNORECASE)
    return text.strip() or message


def determine_edit_type(message: str) -> str:
    """Determina tipo de edición de imagen"""
    message_lower = message.lower()
    if "mejora" in message_lower or "enhance" in message_lower:
        return "enhance"
    elif "blur" in message_lower:
        return "blur"
    else:
        return "ai_edit"


def extract_search_query(message: str) -> str:
    """Extrae query de búsqueda del mensaje"""
    query = re.sub(r'busca\s+(?:en\s+)?(?:mis\s+)?documentos\s+(?:sobre\s+)?', '', message, flags=re.IGNORECASE)
    return query.strip() or message


def extract_email_data(message: str) -> Dict[str, str]:
    """Extrae datos de email del mensaje"""
    # Extraer email destino
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', message)
    to = email_match.group(0) if email_match else "support@example.com"
    
    # Extraer asunto (simplificado)
    subject_match = re.search(r'(?:con|sobre|about)\s+(.+)', message, re.IGNORECASE)
    subject = subject_match.group(1) if subject_match else "Mensaje automático"
    
    return {
        "to": to,
        "subject": subject[:100],
        "body": message
    }


def extract_service_type(message: str) -> str:
    """Extrae tipo de servicio externo"""
    message_lower = message.lower()
    if "google" in message_lower or "drive" in message_lower:
        return "google"
    elif "microsoft" in message_lower or "onedrive" in message_lower:
        return "microsoft"
    elif "github" in message_lower:
        return "github"
    return "google"  # default


def extract_translation_text(message: str) -> str:
    """Extrae texto a traducir"""
    text = re.sub(r'traduce\s+(?:a|al)\s+\w+\s*:?\s*', '', message, flags=re.IGNORECASE)
    return text.strip() or message


def extract_code_request(message: str) -> str:
    """Extrae solicitud de código"""
    request = re.sub(r'genera\s+código\s+(?:en\s+\w+\s+)?(?:para\s+)?', '', message, flags=re.IGNORECASE)
    return request.strip() or message


async def extract_text_from_file(file, vision_service) -> str:
    """Extrae texto de archivo (PDF, DOCX, TXT, imagen con OCR)"""
    try:
        # Si es imagen, usar OCR
        if hasattr(file, 'content_type') and file.content_type.startswith('image/'):
            ocr_result = await vision_service.extract_text(file)
            return ocr_result.get('text', '')
        
        # Si es texto plano
        if hasattr(file, 'read'):
            content = await file.read()
            return content.decode('utf-8')
        
        return str(file)
    except Exception as e:
        logger.error(f"Error extrayendo texto de archivo: {e}")
        return ""
