import asyncio
import logging
import time
from functools import wraps
from typing import Callable, Any, Dict
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError
import aioredis
import os

# ---------------- Logger JSON ----------------
logger = logging.getLogger("resilience")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

# ---------------- Redis ----------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_redis: aioredis.Redis = None
_redis_lock = asyncio.Lock()

async def get_redis() -> aioredis.Redis:
    global _redis
    async with _redis_lock:
        if _redis:
            return _redis
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        try:
            await _redis.ping()
        except Exception:
            logger.warning("[Resilience] Redis no disponible, fail-open activado")
            _redis = None
        return _redis

# ---------------- Circuit Breaker ----------------
_circuit_breakers: Dict[str, "CircuitBreaker"] = {}

class CircuitBreaker:
    """
    Circuit breaker distribuido usando Redis
    """
    def __init__(self, name: str, max_failures: int = 3, reset_timeout: float = 60.0):
        self.name = name
        self.max_failures = max_failures
        self.reset_timeout = reset_timeout

    async def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        redis = await get_redis()
        failures_key = f"cb:{self.name}:failures"
        state_key = f"cb:{self.name}:state"
        last_fail_key = f"cb:{self.name}:last_fail_time"

        state = await redis.get(state_key) if redis else "CLOSED"
        state = state or "CLOSED"
        
        # 🔥 FIX: Evitar double await - obtener valores una sola vez
        failures_value = await redis.get(failures_key) if redis else None
        failures = int(failures_value) if failures_value else 0
        
        last_fail_value = await redis.get(last_fail_key) if redis else None
        last_fail_time = float(last_fail_value) if last_fail_value else 0
        
        now = time.time()

        if state == "OPEN" and now - last_fail_time < self.reset_timeout:
            raise RuntimeError(f"Circuit breaker '{self.name}' abierto")
        elif state == "OPEN":
            state = "HALF-OPEN"
            if redis:
                await redis.set(state_key, state)

        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
        except Exception as e:
            failures += 1
            if redis:
                await redis.set(failures_key, failures)
                await redis.set(last_fail_key, now)
                if failures >= self.max_failures:
                    await redis.set(state_key, "OPEN")
            logger.warning(f"Circuit breaker '{self.name}' fallo: {e}")
            raise
        else:
            if redis:
                await redis.set(failures_key, 0)
                await redis.set(state_key, "CLOSED")
            return result

# ---------------- Decorador ----------------
def resilient(max_attempts: int = 3, wait_min: float = 1.0, wait_max: float = 5.0, cb_name: str = "default"):
    if cb_name not in _circuit_breakers:
        _circuit_breakers[cb_name] = CircuitBreaker(cb_name)
    cb = _circuit_breakers[cb_name]

    def decorator(func: Callable[..., Any]):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            @retry(stop=stop_after_attempt(max_attempts), wait=wait_exponential(min=wait_min, max=wait_max), reraise=True)
            async def wrapped():
                return await cb.call(func, *args, **kwargs) if asyncio.iscoroutinefunction(func) else cb.call(func, *args, **kwargs)
            try:
                return await wrapped()
            except RetryError as e:
                logger.error(f"[Resiliencia] Falló tras {max_attempts} intentos: {e}")
                raise e.last_attempt.exception()
        return wrapper
    return decorator
