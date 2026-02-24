# services/search_service.py
import os
import logging
import httpx
import asyncio
import random
from services.gpt_service import chat_with_ai
# from services.cache_service_enterprise import CacheService  # TODO: Integrar cache enterprise
from aiolimiter import AsyncLimiter

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
SERPAPI_ENABLED = bool(SERPAPI_KEY)

if not SERPAPI_ENABLED:
    logger_warn = logging.getLogger("search_service")
    logger_warn.warning("SERPAPI_KEY no definida en entorno. Búsquedas web deshabilitadas.")

logger = logging.getLogger("search_service")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

# Stubs temporales de cache
async def get_cached_result(user_id: str, key: str):
    """Stub temporal - retorna None (sin cache)"""
    return None

async def set_cached_result(user_id: str, key: str, value: str):
    """Stub temporal - no hace nada"""
    pass

# ---------------- Rate limit por usuario ----------------
user_limiters: dict[str, AsyncLimiter] = {}
def get_limiter(user_id: str) -> AsyncLimiter:
    if user_id not in user_limiters:
        user_limiters[user_id] = AsyncLimiter(5, 1)  # 5 requests por segundo
    return user_limiters[user_id]
# ---------------- Helpers ----------------
async def summarize_chunks(chunks: list, user_id: str) -> str:
    summaries = []
    for chunk in chunks:
        try:
            summary = await chat_with_ai(
                [{"role": "system", "content": f"Resume esta información de internet:\n{chunk}"}],
                user=str(user_id)
            )
            summaries.append(summary.strip())
        except Exception as e:
            logger.warning("Error resumiendo chunk", extra={"user_id": user_id, "error": str(e)})

    final_summary = "\n".join(summaries)
    try:
        final_summary = await chat_with_ai(
            [{"role": "system", "content": f"Combina y sintetiza estos resúmenes:\n{final_summary}"}],
            user=str(user_id)
        )
    except Exception as e:
        logger.warning("Error generando resumen final", extra={"user_id": user_id, "error": str(e)})
    return final_summary.strip()

# ---------------- Función principal ----------------
async def deep_search_web(query: str, user_id: str, num_results_per_page: int = 5, pages: int = 2) -> str:
    cache_key = f"deep_search:{hash(query)}"
    cached = await get_cached_result(user_id, cache_key)
    if cached:
        logger.info("Usando cache", extra={"user_id": user_id, "query": query})
        return cached

    limiter = get_limiter(user_id)
    all_snippets = []

    async with limiter:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                for page in range(pages):
                    params = {
                        "q": query,
                        "num": num_results_per_page,
                        "start": page * num_results_per_page,
                        "api_key": SERPAPI_KEY,
                        "engine": "google"
                    }

                    attempt = 0
                    while attempt < 3:
                        try:
                            response = await client.get("https://serpapi.com/search.json", params=params)
                            response.raise_for_status()
                            data = response.json()
                            results = data.get("organic_results", [])
                            for r in results:
                                title = r.get("title", "").strip()
                                snippet = r.get("snippet", "").strip()
                                link = r.get("link", "").strip()
                                if snippet:
                                    all_snippets.append(f"{title}\n{snippet}\n{link}")
                            break  # éxito, salir del retry loop
                        except Exception as e:
                            attempt += 1
                            delay = (2 ** attempt) + random.random()
                            logger.warning("Error buscando SERPAPI", extra={"user_id": user_id, "attempt": attempt, "error": str(e), "delay": delay})
                            if attempt >= 3:
                                logger.exception("Falló búsqueda SERPAPI después de varios intentos", extra={"user_id": user_id})
                            await asyncio.sleep(delay)

            if not all_snippets:
                return "No se encontraron resultados relevantes."

            # Chunking
            chunk_size = 5
            chunks = ["\n\n".join(all_snippets[i:i+chunk_size]) for i in range(0, len(all_snippets), chunk_size)]

            # Resumen con GPT
            summary = await summarize_chunks(chunks, user_id)

            # Guardar cache
            await set_cached_result(user_id, cache_key, summary)

            return summary

        except Exception as e:
            logger.exception("Error en deep_search_web", extra={"user_id": user_id, "query": query, "error": str(e)})
            return "No se pudo obtener información de Internet en este momento."


# ---------------- Clase SearchService para compatibilidad ----------------
class SearchService:
    """Servicio de búsqueda web"""
    
    def __init__(self):
        self.enabled = SERPAPI_ENABLED
        
    async def search(self, query: str, user_id: str = "default", num_results: int = 5, pages: int = 2) -> str:
        """Búsqueda web con deep search"""
        if not self.enabled:
            return "Búsqueda web no disponible (SERPAPI_KEY no configurada)"
        return await deep_search_web(query, user_id, num_results, pages)
    
    async def health_check(self) -> dict:
        """Health check del servicio"""
        return {
            "service": "search",
            "enabled": self.enabled,
            "status": "ok" if self.enabled else "disabled"
        }
