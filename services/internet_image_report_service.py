# services/internt_image_report_service.py
import asyncio
from io import BytesIO
from typing import List
import httpx
from PIL import Image
import logging
import os

logger = logging.getLogger("advanced_image_service")
logger.setLevel(logging.INFO)

# ---------------- Parámetros ----------------
MIN_WIDTH = 200
MIN_HEIGHT = 200
MAX_IMAGES_PER_PROMPT = 3

# ---------------- Leer API Key del .env ----------------
BING_API_KEY = os.getenv("BING_API_KEY")  # debes agregarlo a tu .env
if not BING_API_KEY:
    logger.warning("No se encontró BING_API_KEY en el .env, la búsqueda no funcionará.")

# ---------------- Funciones de búsqueda ----------------
async def search_images_google(query: str, num: int = 3) -> List[str]:
    """
    Devuelve URLs de imágenes encontradas en Bing (puedes cambiar a Google Custom Search si quieres)
    """
    if not BING_API_KEY:
        return []

    headers = {"Ocp-Apim-Subscription-Key": BING_API_KEY}
    search_url = "https://api.bing.microsoft.com/v7.0/images/search"
    params = {"q": query, "count": num, "safeSearch": "Strict"}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(search_url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        urls = [img["contentUrl"] for img in data.get("value", [])][:num]
    return urls

# ---------------- Funciones de descarga ----------------
async def download_image(url: str) -> BytesIO:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            img = Image.open(BytesIO(resp.content))
            if img.width >= MIN_WIDTH and img.height >= MIN_HEIGHT:
                bio = BytesIO()
                img.save(bio, format="PNG")
                bio.seek(0)
                return bio
    except Exception as e:
        logger.warning(f"Error descargando imagen {url}: {e}")
    return None

async def download_images_parallel(urls: List[str]) -> List[BytesIO]:
    tasks = [download_image(u) for u in urls]
    completed = await asyncio.gather(*tasks, return_exceptions=True)
    images = [c for c in completed if isinstance(c, BytesIO)]
    return images

# ---------------- Función principal para document_service ----------------
async def fetch_images_for_prompts(prompts: List[str], user_id: str, fallback_generate_image=None) -> List[bytes]:
    results = []

    for prompt in prompts:
        urls = await search_images_google(prompt, num=MAX_IMAGES_PER_PROMPT)
        images = await download_images_parallel(urls)

        if not images and fallback_generate_image:
            # Fallback a IA si no hay imágenes encontradas
            logger.info(f"No se encontraron imágenes para '{prompt}', generando con IA...")
            ai_imgs = await fallback_generate_image([{"prompt": prompt}], user_id)
            results.extend(ai_imgs)
        else:
            for img_bio in images:
                results.append(img_bio.getvalue())

    return results

# =============================================
# CLASE PRINCIPAL InternetImageReportService
# =============================================
class InternetImageReportService:
    """Servicio principal de reportes con imágenes de internet"""
    
    def __init__(self):
        self.initialized = True
        logger.info({"event": "internet_image_report_service_initialized"})
    
    async def health_check(self):
        """Health check del servicio"""
        return {
            "status": "ok", 
            "service": "internet_image_report_service",
            "bing_api_available": bool(BING_API_KEY)
        }
    
    async def generate_report_with_images(self, query: str, max_images: int = 5) -> dict:
        """Genera un reporte con imágenes de internet"""
        images = await fetch_images_for_prompts([query], "system")
        
        return {
            "report_title": f"Report for: {query}",
            "images_count": len(images),
            "images_bytes": images,
            "content": f"Generated report content for query: {query}",
            "status": "generated"
        }
    
    async def search_images(self, query: str, count: int = 10) -> List[str]:
        """Busca imágenes en internet"""
        return await search_images_google(query, count)

# Instancia global
internet_image_report_service = InternetImageReportService()
