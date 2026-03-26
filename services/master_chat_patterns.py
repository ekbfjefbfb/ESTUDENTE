"""
Master Chat Patterns - Intent detection patterns
Separado de master_chat_service.py para reducir responsabilidades
"""
import re
from typing import Dict, List, Any

# ====================================
# PATRONES DE DETECCIÓN AUTOMÁTICA v4.0 (17 CAPACIDADES)
# ====================================

AUTO_PATTERNS: Dict[str, List[str]] = {
    # ====================================
    # 🎨 CAPACIDADES ORIGINALES (7)
    # ====================================
    "generate_image": [
        r"crea\s+(?:una\s+)?imagen",
        r"genera\s+(?:una\s+)?imagen", 
        r"dibuja\s+(?:una\s+)?imagen",
        r"haz\s+(?:una\s+)?imagen",
        r"create\s+(?:an?\s+)?image",
        r"generate\s+(?:an?\s+)?image"
    ],
    "edit_image": [
        r"edita\s+(?:la\s+)?imagen",
        r"mejora\s+(?:la\s+)?imagen",
        r"modifica\s+(?:la\s+)?imagen",
        r"cambia\s+(?:la\s+)?imagen"
    ],
    "create_document": [
        r"crea\s+(?:un\s+)?(?:pdf|documento)",
        r"genera\s+(?:un\s+)?(?:pdf|documento)",
        r"haz\s+(?:un\s+)?(?:pdf|documento)",
        r"créame\s+(?:un\s+)?(?:pdf|documento)"
    ],
    "text_to_speech": [
        r"convierte\s+(?:a\s+)?(?:voz|audio)",
        r"lee\s+(?:este\s+)?texto",
        r"text\s+to\s+speech",
        r"dilo\s+en\s+voz"
    ],
    "analyze_image": [
        r"analiza\s+(?:la\s+)?imagen",
        r"qué\s+(?:hay\s+)?(?:en\s+)?(?:la\s+)?imagen",
        r"describe\s+(?:la\s+)?imagen",
        r"explica\s+(?:la\s+)?imagen"
    ],
    
    # ====================================
    # 🚀 NUEVAS CAPACIDADES v4.0 (10)
    # ====================================
    
    # 1. Detección de objetos
    "detect_objects": [
        r"detecta\s+(?:objetos|cosas)",
        r"qué\s+objetos\s+hay",
        r"encuentra\s+(?:objetos|cosas)",
        r"detect\s+objects",
        r"identifica\s+objetos"
    ],
    
    # 2. Detección de rostros
    "detect_faces": [
        r"detecta\s+(?:rostros|caras|personas)",
        r"cuántas\s+personas\s+hay",
        r"reconocimiento\s+facial",
        r"detect\s+faces",
        r"identificar\s+rostros"
    ],
    
    # 3. Búsqueda en documentos
    "search_documents": [
        r"busca\s+en\s+(?:mis\s+)?documentos",
        r"encuentra\s+(?:en\s+)?(?:mis\s+)?documentos",
        r"qué\s+dice\s+mi\s+documento\s+sobre",
        r"search\s+in\s+(?:my\s+)?documents",
        r"consulta\s+(?:mis\s+)?documentos"
    ],
    
    # 4. Envío de emails
    "send_email": [
        r"envía\s+(?:un\s+)?(?:email|correo)",
        r"manda\s+(?:un\s+)?(?:email|correo)",
        r"send\s+(?:an?\s+)?email",
        r"escribe\s+(?:un\s+)?email\s+a"
    ],
    
    # 5. Sincronización con servicios externos
    "sync_external": [
        r"sincroniza\s+(?:con\s+)?(?:google|microsoft|github)",
        r"sube\s+a\s+(?:drive|onedrive|github)",
        r"guarda\s+en\s+(?:google|microsoft|drive)",
        r"sync\s+with",
        r"exporta\s+a\s+(?:google|microsoft)"
    ],
    
    # 6. Traducción
    "translate_text": [
        r"traduce\s+(?:a|al)\s+\w+",
        r"translate\s+to\s+\w+",
        r"en\s+\w+\s+(?:por\s+favor|please)",
        r"cómo\s+se\s+dice\s+en\s+\w+",
        r"pásalo\s+a\s+\w+"
    ],
    
    # 7. Resumen de textos
    "summarize_text": [
        r"resume\s+(?:este\s+)?(?:texto|documento)",
        r"haz\s+un\s+resumen",
        r"summarize\s+(?:this\s+)?(?:text|document)",
        r"dame\s+un\s+resumen",
        r"sintetiza\s+(?:este\s+)?(?:texto|documento)"
    ],
    
    # 8. Generación de código
    "generate_code": [
        r"genera\s+código\s+(?:en\s+)?(\w+)?",
        r"escribe\s+(?:un\s+)?script\s+(?:en\s+)?(\w+)?",
        r"create\s+(?:a\s+)?script",
        r"programa\s+(?:en\s+)?(\w+)?",
        r"código\s+para"
    ],
    
    # 9. Extracción de datos
    "extract_data": [
        r"extrae\s+(?:datos|información)",
        r"lee\s+(?:los\s+)?datos\s+de",
        r"extract\s+data\s+from",
        r"obtén\s+(?:los\s+)?datos",
        r"saca\s+la\s+información"
    ],
    
    # 10. Comparación de documentos
    "compare_documents": [
        r"compara\s+(?:estos\s+)?documentos",
        r"diferencias\s+entre",
        r"compare\s+(?:these\s+)?documents",
        r"qué\s+cambió\s+entre",
        r"contrasta\s+(?:estos\s+)?documentos"
    ]
}


def detect_intents_by_patterns(message: str, files: List[Any] = None) -> List[str]:
    """Detecta intenciones por patrones regex"""
    message_lower = message.lower()
    detected_intents = []
    
    for intent_type, patterns in AUTO_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, message_lower):
                detected_intents.append(intent_type)
                break
    
    # Detección por archivos subidos
    if files:
        for file in files:
            if file and hasattr(file, 'content_type'):
                if file.content_type.startswith('image/'):
                    if not any(intent in detected_intents for intent in ['edit_image', 'analyze_image']):
                        detected_intents.append('analyze_image')
    
    return detected_intents


def get_intent_display_name(intent: str) -> str:
    """Obtiene nombre legible de una intención"""
    display_names = {
        "generate_image": "🎨 Generar Imagen",
        "edit_image": "✨ Editar Imagen",
        "create_document": "📄 Crear Documento",
        "text_to_speech": "🎵 Texto a Voz",
        "analyze_image": "👁️ Analizar Imagen",
        "detect_objects": "🔍 Detectar Objetos",
        "detect_faces": "👤 Detectar Rostros",
        "search_documents": "📚 Buscar Documentos",
        "send_email": "📧 Enviar Email",
        "sync_external": "☁️ Sincronizar Externo",
        "translate_text": "🌐 Traducir Texto",
        "summarize_text": "📝 Resumir Texto",
        "generate_code": "💻 Generar Código",
        "extract_data": "📊 Extraer Datos",
        "compare_documents": "🔍 Comparar Documentos",
        "general_chat": "💬 Chat General"
    }
    return display_names.get(intent, intent)
