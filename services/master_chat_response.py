"""
Master Chat Response - Smart response creation
Separado de master_chat_service.py para reducir responsabilidades
"""
from typing import Dict, Any, List


def create_smart_response(
    intent_analysis: Dict,
    results: Dict,
    original_message: str
) -> str:
    """
    Crea respuesta inteligente que menciona todo lo que se generó automáticamente
    🚀 v4.0 - Con 17 capacidades
    """
    base_response = results.get("chat_response", "")
    
    # Agregar información sobre lo que se generó automáticamente
    auto_actions = []
    
    # Capacidades originales
    if results.get("generated_image"):
        auto_actions.append("🎨 He generado una imagen según tu solicitud")
    
    if results.get("edited_image"):
        auto_actions.append("✨ He editado la imagen que subiste")
    
    if results.get("document"):
        auto_actions.append("📄 He creado un documento sobre el tema")
    
    if results.get("image_analysis"):
        analysis = results["image_analysis"]
        auto_actions.append(f"👁️ He analizado la imagen: {analysis}")
    
    if results.get("audio"):
        auto_actions.append("🎵 He convertido el texto a audio")
    
    # Nuevas capacidades v4.0
    if results.get("detected_objects"):
        obj_count = len(results["detected_objects"].get("objects", []))
        auto_actions.append(f"🔍 He detectado {obj_count} objetos en la imagen")
    
    if results.get("detected_faces"):
        face_count = results["detected_faces"].get("face_count", 0)
        auto_actions.append(f"👤 He detectado {face_count} persona(s) en la imagen")
    
    if results.get("search_results"):
        result_count = len(results["search_results"].get("results", []))
        auto_actions.append(f"📚 He encontrado {result_count} resultados en tus documentos")
    
    if results.get("email_sent"):
        auto_actions.append("📧 He enviado el email automáticamente")
    
    if results.get("sync_result"):
        service = results["sync_result"].get("service", "servicio externo")
        auto_actions.append(f"☁️ He sincronizado el archivo con {service}")
    
    if results.get("translation"):
        lang = results["translation"].get("target_language", "otro idioma")
        auto_actions.append(f"🌐 He traducido el texto a {lang}")
    
    if results.get("summary"):
        ratio = results["summary"].get("compression_ratio", 0)
        auto_actions.append(f"📝 He resumido el texto ({ratio:.0%} del original)")
    
    if results.get("code"):
        language = results["code"].get("language", "código")
        auto_actions.append(f"💻 He generado código en {language}")
    
    if results.get("extracted_data"):
        field_count = len(results["extracted_data"].get("fields", []))
        auto_actions.append(f"📊 He extraído {field_count} campos de datos")
    
    if results.get("comparison"):
        auto_actions.append("🔍 He comparado los documentos")
    
    # Combinar respuesta
    if auto_actions:
        actions_text = "\n\n" + "\n".join(auto_actions)
        return base_response + actions_text
    
    return base_response


def extract_generated_content(results: Dict) -> Dict[str, Any]:
    """Extrae contenido generado para la respuesta"""
    content = {}
    
    if results.get("generated_image"):
        content["image"] = results["generated_image"]
    
    if results.get("edited_image"):
        content["edited_image"] = results["edited_image"]
    
    if results.get("document"):
        content["document"] = results["document"]
    
    if results.get("audio"):
        content["audio"] = results["audio"]
    
    return content


def extract_generated_files(results: Dict) -> List[Dict[str, Any]]:
    """Extrae archivos generados"""
    files = []
    
    if results.get("generated_image"):
        files.append({
            "type": "image",
            "data": results["generated_image"],
            "description": "Imagen generada automáticamente"
        })
    
    if results.get("edited_image"):
        files.append({
            "type": "image", 
            "data": results["edited_image"],
            "description": "Imagen editada automáticamente"
        })
    
    if results.get("document"):
        files.append({
            "type": "document",
            "data": results["document"],
            "description": "Documento creado automáticamente"
        })
    
    if results.get("audio"):
        files.append({
            "type": "audio",
            "data": results["audio"],
            "description": "Audio generado automáticamente"
        })
    
    return files


def create_execution_summary(results: Dict) -> str:
    """Crea resumen de ejecución"""
    actions = []
    
    if results.get("generated_image"):
        actions.append("Imagen generada")
    if results.get("edited_image"):
        actions.append("Imagen editada")
    if results.get("document"):
        actions.append("Documento creado")
    if results.get("image_analysis"):
        actions.append("Imagen analizada")
    if results.get("audio"):
        actions.append("Audio generado")
    if results.get("chat_response"):
        actions.append("Respuesta de chat")
    
    return f"Ejecutado automáticamente: {', '.join(actions)}" if actions else "Chat procesado"
