"""
Chat Search - Web search utilities for chat
Separado de unified_chat_router.py para reducir responsabilidades
"""
import logging
import time
import re
from typing import Dict, Any, List

logger = logging.getLogger("chat_search")

# Palabras / patrones que sugieren datos externos (ES + EN)
_WEB_SEARCH_TRIGGERS = [
    "busca", "buscar", "búsqueda", "encuentra", "encontrar", "investiga", "investigar",
    "qué es", "que es", "quien es", "quién es", "quién fue", "quien fue",
    "como se", "cómo se", "donde", "dónde", "cuando", "cuándo",
    "noticias", "actualidad", "hoy", "ahora", "última hora", "ultima hora",
    "precio", "costo", "cuanto cuesta", "cuánto cuesta", "cotización", "bolsa",
    "imagen", "imágenes", "foto", "fotos",
    "weather", "clima", "temperatura",
    "search", "google", "internet", "online", "web ", "lookup", "look up",
    "latest", "update", "current", "reciente", "actualizado",
    "verify", "verifica", "verificar", "comprueba", "fuente", "referencia", "source",
    "wiki", "wikipedia", "reddit",
    "who is", "what is", "when did", "where is", "how much", "how many",
    "stock", "earnings", "released",
]


def _should_web_search(*, user_id: str, message: str, force: bool = False) -> bool:
    """Determina si se debe hacer búsqueda web (prefetch) según el mensaje o force."""
    if force:
        return True
    msg = str(message or "").lower()
    if any(t in msg for t in _WEB_SEARCH_TRIGGERS):
        return True
    # Años recientes → hechos que cambian (noticias, versiones, leyes)
    if re.search(r"\b20[2-3]\d\b", msg):
        return True
    # Preguntas largas suelen ser factuales
    if msg.rstrip().endswith("?") and len(msg) > 45:
        return True
    return False


def _should_include_images_in_search(message: str) -> bool:
    """Determina si el usuario pidió imágenes"""
    msg = str(message or "").lower()
    triggers = ["imagen", "imágenes", "foto", "fotos", "picture", "image", "photo"]
    return any(t in msg for t in triggers)


def _user_requested_images(message: str) -> bool:
    """Alias para _should_include_images_in_search"""
    return _should_include_images_in_search(message)


def _safe_meta(meta: Any) -> Dict[str, Any]:
    """Extrae campos seguros de metadata"""
    if not isinstance(meta, dict):
        return {}
    out: Dict[str, Any] = {}
    for k in ("status", "attempt", "key_index", "fallback", "attempts"):
        if k in meta:
            out[k] = meta.get(k)
    return out


def _should_use_semantic_cache(message: str) -> bool:
    """Determina si usar cache semántico"""
    # No cachear preguntas sobre tiempo, noticias, o precios (datos cambiantes)
    msg = str(message or "").lower()
    temporal_keywords = [
        "hoy", "ahora", "actualidad", "noticias", "tiempo", "clima",
        "temperatura", "precio", "precios", "cotización", "dólar", "euro"
    ]
    if any(kw in msg for kw in temporal_keywords):
        return False
    if _should_web_search(user_id="", message=msg):
        return False
    if msg.rstrip().endswith("?") and len(msg) > 45:
        return False
    return True


def _normalize_message_text(message: str) -> str:
    """Normaliza texto de mensaje"""
    if not message:
        return ""
    # Remover emojis múltiples, normalizar espacios
    text = re.sub(r'\s+', ' ', message).strip()
    return text[:8000]


async def perform_web_search(
    user_id: str,
    query: str,
    include_images: bool = False
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Realiza búsqueda web con fallback: Tavily -> Serper -> DDG
    Retorna: (sources, metadata)
    """
    ws_t0 = time.monotonic()
    
    from services.tavily_search_service import tavily_search_service
    from services.serper_search_service import serper_search_service
    
    tavily_sources: List[Dict[str, Any]] = []
    tavily_meta: Dict[str, Any] = {"status": "disabled"}
    
    # 1) Tavily (primario) con rotación por user_id
    if tavily_search_service.enabled():
        try:
            tavily_sources, tavily_meta = await tavily_search_service.search_with_meta(
                query=query.strip(),
                user_id=str(user_id),
                include_images=include_images,
            )
        except Exception:
            tavily_sources = []
            tavily_meta = {"status": "failed"}
    
    if tavily_sources:
        return tavily_sources, {"provider": "tavily", "meta": tavily_meta}
    
    # 2) Serper (secundario)
    serper_sources = []
    if serper_search_service.enabled():
        try:
            serper_sources, serper_meta = await serper_search_service.search_with_meta(
                query=query.strip(),
                user_id=str(user_id),
                include_images=include_images,
            )
        except Exception:
            serper_sources = []
            serper_meta = {"status": "failed"}
    
    if serper_sources:
        logger.info(
            f"web_search_provider user_id={user_id} provider=serper "
            f"meta={_safe_meta(serper_meta)} results={len(serper_sources)} "
            f"duration_ms={int((time.monotonic()-ws_t0)*1000)}"
        )
        return serper_sources, {"provider": "serper", "meta": serper_meta}
    
    return [], {"provider": "none", "meta": {"status": "failed"}}

async def perform_agentic_research(user_id: str, query: str) -> str:
    """
    Realiza una investigación profunda usando el equipo de agentes.
    1) Busca en la web. 2) Los agentes sintetizan el informe.
    """
    try:
        from services.agent_service import agent_manager
        
        # Primero obtenemos las fuentes crudas
        sources, _ = await perform_web_search(user_id, query)
        
        if not sources:
            return "No se encontraron fuentes confiables para esta investigación."
            
        # Contexto de búsqueda para los agentes
        context = "\n".join([f"- [{s.get('title')}]({s.get('url')}): {s.get('content', '')[:300]}" for s in sources[:5]])
        
        task_desc = f"""
        Realiza una investigación profunda sobre: "{query}"
        Utiliza estas fuentes como base:
        {context}
        
        Tu objetivo:
        - Sintetizar los puntos clave de todas las fuentes.
        - Identificar tendencias o datos críticos.
        - Generar un informe estructurado y profesional.
        """
        
        logger.info(f"chat_search: Iniciando Investigación Agéntica (USER:{user_id})")
        
        # Ejecutar ciclo agéntico
        result = await agent_manager.run_complex_task(task_desc, user_id=user_id)
        
        if result and hasattr(result, "summary"):
            return result.summary
            
        return "Informe generado tras el análisis agéntico de las fuentes."
        
    except Exception as e:
        logger.error(f"Error en investigación agéntica: {e}")
        return f"Investigación fallida sobre: {query}"


def prioritize_sources_with_images(sources: List[Dict[str, Any]], max_sources: int = 5) -> List[Dict[str, Any]]:
    """Prioriza fuentes con imágenes"""
    if not sources:
        return []
    
    prioritized = []
    remainder = []
    
    for s in sources:
        if not isinstance(s, dict):
            continue
        if str(s.get("image") or s.get("image_url") or "").strip():
            prioritized.append(s)
        else:
            remainder.append(s)
    
    return (prioritized + remainder)[:max_sources]
