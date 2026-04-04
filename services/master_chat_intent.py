"""
Master Chat Intent - Intent detection logic
Separado de master_chat_service.py para reducir responsabilidades
"""
import logging
from typing import Dict, List, Optional, Any

from services.groq_ai_service import chat_with_ai, sanitize_ai_text
from services.master_chat_patterns import detect_intents_by_patterns
from config import AI_MODEL

logger = logging.getLogger("master_chat_intent")


async def detect_intentions(
    message: str,
    files: Optional[List] = None
) -> Dict[str, Any]:
    """
    Detección AUTOMÁTICA de todas las intenciones del usuario
    Combina: patrones regex + detección por archivos + IA inteligente
    """
    # 1. Detección por patrones
    detected_intents = detect_intents_by_patterns(message, files)
    
    # 2. Detección inteligente con IA
    ai_intents = await _ai_smart_detection(message)
    detected_intents.extend(ai_intents)
    
    # 3. Siempre incluir chat si no hay otras intenciones
    if not detected_intents:
        detected_intents.append('general_chat')
    elif 'general_chat' not in detected_intents:
        detected_intents.append('general_chat')  # Chat + otras acciones
    
    # 4. Extraer parámetros inteligentes
    parameters = extract_smart_parameters(message)
    
    return {
        "intents": list(set(detected_intents)),
        "primary_intent": detected_intents[0] if detected_intents else "general_chat",
        "auto_mode": True,
        "parameters": parameters,
        "confidence": len(detected_intents) * 0.3
    }


async def _ai_smart_detection(message: str) -> List[str]:
    """IA inteligente para detectar intenciones complejas"""
    try:
        detection_prompt = f"""
        Analiza este mensaje del usuario y detecta QUÉ QUIERE HACER:
        "{message}"
        
        Responde SOLO con intenciones separadas por comas de esta lista:
        - generate_image (si quiere crear/generar una imagen)
        - edit_image (si quiere editar/mejorar una imagen)
        - create_document (si quiere crear PDF/documento)
        - text_to_speech (si quiere convertir texto a voz)
        - analyze_image (si quiere analizar una imagen)
        - general_chat (conversación normal)
        
        Ejemplo: "generate_image, general_chat"
        """
        
        ai_response = await chat_with_ai(
            messages=[{"role": "user", "content": detection_prompt}],
            model=AI_MODEL
        )
        ai_response = sanitize_ai_text(ai_response)
        
        # Parsear respuesta de la IA
        intents = [intent.strip() for intent in ai_response.split(",")]
        valid_intents = [
            intent for intent in intents 
            if intent in ["generate_image", "edit_image", "create_document", 
                         "text_to_speech", "analyze_image", "general_chat"]
        ]
        
        return valid_intents
        
    except Exception as e:
        logger.error(f"Error en detección IA: {e}")
        return []


def extract_smart_parameters(message: str) -> Dict[str, Any]:
    """Extrae parámetros inteligentes del mensaje"""
    import re
    parameters = {}
    
    # Dimensiones de imagen
    size_match = re.search(r'(\d+)x(\d+)', message)
    if size_match:
        parameters["width"] = int(size_match.group(1))
        parameters["height"] = int(size_match.group(2))
    
    # Formato de documento
    if "pdf" in message.lower():
        parameters["format"] = "pdf"
    elif "word" in message.lower() or "docx" in message.lower():
        parameters["format"] = "docx"
    
    # Idioma destino para traducción
    lang_match = re.search(
        r'(?:a|al|to)\s+(inglés|español|francés|alemán|italiano|portugués|english|spanish|french|german|italian|portuguese)',
        message, re.IGNORECASE
    )
    if lang_match:
        lang_map = {
            "inglés": "en", "english": "en",
            "español": "es", "spanish": "es",
            "francés": "fr", "french": "fr",
            "alemán": "de", "german": "de",
            "italiano": "it", "italian": "it",
            "portugués": "pt", "portuguese": "pt"
        }
        parameters["target_language"] = lang_map.get(lang_match.group(1).lower(), "en")
    
    # Lenguaje de programación
    code_lang_match = re.search(
        r'(?:en|in)\s+(python|javascript|java|c\+\+|ruby|go|rust|php|swift)',
        message, re.IGNORECASE
    )
    if code_lang_match:
        parameters["language"] = code_lang_match.group(1).lower()
    
    return parameters
