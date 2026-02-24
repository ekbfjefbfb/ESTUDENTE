# services/stability_service_batch.py
import logging
import httpx
import base64
import uuid
import hashlib
import time
import asyncio
from typing import Optional, List, Dict, Any, Callable
from aiolimiter import AsyncLimiter
from utils.safe_metrics import Counter, Histogram
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential, retry_if_exception_type
from services.gateways.visa_gateway import VisaGateway

from services.redis_service import redis, init_redis, redis_set, redis_get, _get_lock  # Redis centralizado

import json_log_formatter
import os

# ---------------- Logging JSON ----------------
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("stability_service_batch")
logger.addHandler(handler)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

# ---------------- Configuración ----------------
STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")
HF_API_TOKEN = os.getenv("HF_API_TOKEN")
STABILITY_API_URL = "https://api.stability.ai/v1/generation/text-to-image"
HF_API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-2"

CACHE_EXPIRE = int(os.getenv("CACHE_EXPIRE", 3600))
ERROR_LOG_EXPIRE = int(os.getenv("ERROR_LOG_EXPIRE", 86400))  # 1 día

MAX_PROMPT_LENGTH = 1000
MAX_WIDTH = 1024
MAX_HEIGHT = 1024
MIN_WIDTH = 64
MIN_HEIGHT = 64
MAX_STEPS = 50
MIN_STEPS = 1

BATCH_TIMEOUT = int(os.getenv("BATCH_TIMEOUT", 120))
CONCURRENCY_LIMIT = int(os.getenv("CONCURRENCY_LIMIT", 20))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 60))

# ---------------- Prometheus ----------------
IMAGE_GENERATED_COUNTER = Counter('images_generated_total', 'Total images generated', ['user_id', 'service'])
IMAGE_FAILED_COUNTER = Counter('images_failed_total', 'Total failed image generations', ['user_id', 'service'])
IMAGE_GENERATION_HIST = Histogram('image_generation_duration_seconds', 'Duration of image generation', ['user_id', 'service'])
BATCH_DURATION_HIST = Histogram('batch_generation_duration_seconds', 'Duration of batch generation', ['user_id'])
IMAGE_SIZE_HIST = Histogram('image_size_bytes', 'Size of generated images', ['user_id', 'service'])
RETRY_COUNTER = Counter('image_retry_total', 'Number of retries per image', ['user_id', 'service'])

# ---------------- Rate Limiter ----------------
user_limiters: Dict[str, AsyncLimiter] = {}
def get_user_limiter(user_id: str, max_calls: int = 5, per_seconds: int = 10) -> AsyncLimiter:
    if user_id not in user_limiters:
        user_limiters[user_id] = AsyncLimiter(max_calls, per_seconds)
    return user_limiters[user_id]

# ---------------- Helpers ----------------
def _cache_key(prompt: str, width: int, height: int, steps: int) -> str:
    return hashlib.md5(f"{prompt}_{width}_{height}_{steps}".encode("utf-8")).hexdigest()

def _truncate_prompt(prompt: str) -> str:
    if len(prompt) > MAX_PROMPT_LENGTH:
        logger.warning({"event": "prompt_truncated", "original_length": len(prompt)})
        return prompt[:MAX_PROMPT_LENGTH]
    return prompt

def _validate_prompt_dimensions(prompt: str, width: int, height: int, steps: int):
    if not prompt.strip():
        raise ValueError("Prompt vacío")
    prompt = _truncate_prompt(prompt)
    width = max(MIN_WIDTH, min(MAX_WIDTH, width))
    height = max(MIN_HEIGHT, min(MAX_HEIGHT, height))
    steps = max(MIN_STEPS, min(MAX_STEPS, steps))
    return width, height, steps

async def _save_image(user_id: str, image_bytes: bytes, prompt: Optional[str] = None) -> str:
    prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8] if prompt else ""
    title = f"image_{prompt_hash}_{uuid.uuid4().hex[:4]}.png" if prompt else f"image_{uuid.uuid4().hex[:8]}.png"
    cache_key = f"user:{user_id}:image:{title}"
    async with _get_lock(cache_key):
        await redis_set(cache_key, image_bytes, CACHE_EXPIRE)
    IMAGE_SIZE_HIST.labels(user_id=user_id, service="save").observe(len(image_bytes))
    logger.info({"event": "image_saved", "user_id": user_id, "title": title, "size_bytes": len(image_bytes)})
    return title

async def log_error(user_id: str, error_data: Dict[str, Any]):
    if not redis:
        await init_redis()
    error_id = f"{user_id}:error:{uuid.uuid4().hex}"
    async with _get_lock(error_id):
        await redis_set(error_id, error_data, ERROR_LOG_EXPIRE)

# ---------------- Retry inteligente ----------------
async def retry_async_call(coro_func, user_id: str, service: str, *args, **kwargs):
    async for attempt in AsyncRetrying(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type(Exception)
    ):
        with attempt:
            try:
                result = await coro_func(*args, **kwargs)
                return result
            except Exception as e:
                RETRY_COUNTER.labels(user_id=user_id, service=service).inc()
                logger.warning({
                    "event": "retry_attempt",
                    "user_id": user_id,
                    "service": service,
                    "error": str(e),
                    "attempt": attempt.retry_state.attempt_number
                })
                await log_error(user_id, {"service": service, "error": str(e), "attempt": attempt.retry_state.attempt_number})
                raise

# ---------------- Servicio de generación ----------------
async def _generate_image_service(user_id: str, prompt: str, width: int, height: int, steps: int, service: str) -> Optional[bytes]:
    if service == "stability" and not STABILITY_API_KEY:
        return None
    if service == "hf" and not HF_API_TOKEN:
        return None

    headers = {"Content-Type": "application/json"}
    url = STABILITY_API_URL if service == "stability" else HF_API_URL
    if service == "stability": headers["Authorization"] = f"Bearer {STABILITY_API_KEY}"
    if service == "hf": headers["Authorization"] = f"Bearer {HF_API_TOKEN}"

    payload = {"prompt": prompt, "width": width, "height": height, "steps": steps, "samples": 1} if service == "stability" else {"inputs": prompt}

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            start = time.time()
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            duration = time.time() - start
            IMAGE_GENERATION_HIST.labels(user_id=user_id, service=service).observe(duration)

            data = resp.json()
            if service == "stability" and data.get("artifacts") and data["artifacts"][0].get("base64"):
                IMAGE_GENERATED_COUNTER.labels(user_id=user_id, service=service).inc()
                return base64.b64decode(data["artifacts"][0]["base64"])
            elif service == "hf" and isinstance(data, list) and data and "generated_image" in data[0]:
                IMAGE_GENERATED_COUNTER.labels(user_id=user_id, service=service).inc()
                return base64.b64decode(data[0]["generated_image"])
    except Exception as e:
        IMAGE_FAILED_COUNTER.labels(user_id=user_id, service=service).inc()
        logger.warning({
            "event": f"{service}_failure",
            "user_id": user_id,
            "prompt_hash": hashlib.md5(prompt.encode()).hexdigest(),
            "error": str(e)
        })
        await log_error(user_id, {"service": service, "prompt": prompt, "error": str(e)})
    return None

# ---------------- Generación single con cache ----------------
async def _generate_and_save_single(prompt_info: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    prompt_text = prompt_info.get("prompt", "")
    width, height, steps = _validate_prompt_dimensions(
        prompt_text,
        prompt_info.get("width", 512),
        prompt_info.get("height", 512),
        prompt_info.get("steps", 30)
    )
    meta = {"prompt": prompt_text, "width": width, "height": height, "steps": steps}

    key = _cache_key(prompt_text, width, height, steps)
    cached = await redis_get(f"user:{user_id}:cache:{key}")
    if cached:
        meta.update({"title": "cached_image", "status": "success", "error": None})
        return meta

    image_bytes = None
    for service in ["stability", "hf"]:
        image_bytes = await retry_async_call(_generate_image_service, user_id, service, user_id, prompt_text, width, height, steps, service)
        if image_bytes:
            break

    if image_bytes:
        title = await _save_image(user_id, image_bytes, prompt_text)
        await redis_set(f"user:{user_id}:cache:{key}", image_bytes, CACHE_EXPIRE)
        meta.update({"title": title, "status": "success", "error": None})
    else:
        meta.update({"title": None, "status": "failed", "error": "Ningún servicio disponible"})
    return meta

# ---------------- Batch masivo cancelable ----------------
class BatchController:
    """Permite cancelar un batch desde fuera"""
    def __init__(self):
        self._cancel_event = asyncio.Event()
    def cancel(self):
        self._cancel_event.set()
    async def is_cancelled(self):
        return self._cancel_event.is_set()

async def generate_images_batch(
    prompts: List[Dict[str, Any]],
    user_id: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    controller: Optional[BatchController] = None
) -> List[Dict[str, Any]]:
    limiter = get_user_limiter(user_id)
    batch_start = time.time()
    results: List[Dict[str, Any]] = []
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    async def sem_task(p, index):
        async with semaphore:
            if controller and await controller.is_cancelled():
                return {"title": None, "prompt": p.get("prompt", ""), "width": None, "height": None, "steps": None, "status": "cancelled", "error": "Batch cancelado"}
            result = await _generate_and_save_single(p, user_id)
            if progress_callback:
                progress_callback(index + 1, len(prompts))
            return result

    async with limiter:
        tasks = [asyncio.create_task(sem_task(p, i)) for i, p in enumerate(prompts)]
        for coro in asyncio.as_completed(tasks, timeout=BATCH_TIMEOUT):
            try:
                res = await coro
                results.append(res)
            except asyncio.TimeoutError:
                results.append({"title": None, "prompt": "unknown", "width": None, "height": None, "steps": None, "status": "failed", "error": "Timeout"})
            except Exception as e:
                results.append({"title": None, "prompt": "unknown", "width": None, "height": None, "steps": None, "status": "failed", "error": str(e)})

    BATCH_DURATION_HIST.labels(user_id=user_id).observe(time.time() - batch_start)
    logger.info({"event": "batch_completed", "user_id": user_id, "num_prompts": len(prompts), "duration_sec": time.time() - batch_start})
    return results

# =============================================
# CLASE PRINCIPAL StabilityService
# =============================================
class StabilityService:
    """Servicio principal de Stability AI"""
    
    def __init__(self):
        self.initialized = True
        logger.info({"event": "stability_service_initialized"})
    
    async def health_check(self):
        """Health check del servicio"""
        return {
            "status": "ok", 
            "service": "stability_service",
            "api_available": bool(STABILITY_API_KEY)
        }
    
    async def generate_image(self, prompt: str, **kwargs) -> dict:
        """Genera una imagen usando Stability AI"""
        prompts = [{"prompt": prompt, **kwargs}]
        results = await generate_images_batch(prompts, "system")
        return results[0] if results else {"error": "Generation failed"}
    
    async def generate_batch(self, prompts: list, user_id: str) -> list:
        """Genera múltiples imágenes en lote"""
        return await generate_images_batch(prompts, user_id)

# Instancia global
stability_service = StabilityService()
