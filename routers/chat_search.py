"""
Chat Search - Web search utilities for chat
Separado de unified_chat_router.py para reducir responsabilidades
"""
import logging
import time
import re
from typing import Dict, Any, List

logger = logging.getLogger("chat_search")


def _should_web_search(*, user_id: str, message: str) -> bool:
    """Determina si se debe hacer búsqueda web basado en el mensaje"""
    msg = str(message or "").lower()
    triggers = [
        "busca", "buscar", "encuentra", "encontrar",
        "qué es", "que es", "quien es", "quién es",
        "como se", "cómo se", "donde", "dónde",
        "noticias", "actualidad", "hoy", "ahora",
        "precio", "costo", "cuanto cuesta", "cuánto cuesta",
        "imagen", "imágenes", "foto", "fotos",
        "weather", "clima", "temperatura"
    ]
    return any(t in msg for t in triggers)


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
