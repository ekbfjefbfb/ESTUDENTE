# middlewares/rate_limit_middleware.py
import os
import logging
import json
import jwt
import aioredis
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.status import HTTP_429_TOO_MANY_REQUESTS
from sqlalchemy.future import select
from database.db_enterprise import get_primary_session as get_async_db
from models.models import User
from utils.metrics import REQUESTS_TOTAL, RATE_LIMIT_HITS  # métricas centralizadas

# ---------------- Logger JSON ----------------
class JsonFormatter(logging.Formatter):
    def format(self, record):
        if isinstance(record.msg, dict):
            record.msg = json.dumps(record.msg)
        return super().format(record)

logger = logging.getLogger("rate_limit_middleware")
if not logger.hasHandlers():
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))
    ch = logging.StreamHandler()
    ch.setFormatter(JsonFormatter())
    logger.addHandler(ch)

# ---------------- Configuración ----------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
JWT_SECRET = os.getenv("JWT_SECRET", "default-jwt-secret-change-in-production")
if not JWT_SECRET or JWT_SECRET == "default-jwt-secret-change-in-production":
    logger.warning("JWT_SECRET no configurado o usando valor por defecto. Configure JWT_SECRET en producción.")
JWT_ALGORITHM = "HS256"

# ---------------- Planes base ----------------
DEFAULT_PLAN_LIMITS = {
    "demo": {"max_requests": 5, "window_seconds": 60},
    "basic": {"max_requests": 20, "window_seconds": 60},
    "pro": {"max_requests": 100, "window_seconds": 60},
}

# ---------------- LUA Script para atomicidad ----------------
LUA_RATE_LIMIT = """
local current = redis.call("INCR", KEYS[1])
if current == 1 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
end
return current
"""

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware global de rate limiting avanzado por usuario/IP/plan"""

    def __init__(self, app, redis_url: str = REDIS_URL):
        super().__init__(app)
        self.redis_url = redis_url
        self.redis = None

    async def _get_redis(self):
        if not self.redis:
            self.redis = await aioredis.from_url(self.redis_url, decode_responses=True)
        return self.redis

    def _get_user_id_from_jwt(self, request: Request):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return int(payload.get("user_id"))
        except Exception:
            return None

    async def _get_plan_limits(self, user_id: int):
        if not user_id:
            return DEFAULT_PLAN_LIMITS["demo"]
        try:
            async with get_async_db() as db:
                result = await db.execute(select(User).where(User.id == user_id))
                user: User = result.scalar_one_or_none()
                if user and user.plan:
                    plan_name = user.plan.name.lower().strip()
                    return getattr(user.plan, "limits", DEFAULT_PLAN_LIMITS.get(plan_name, DEFAULT_PLAN_LIMITS["demo"]))
        except Exception:
            return DEFAULT_PLAN_LIMITS["demo"]
        return DEFAULT_PLAN_LIMITS["demo"]

    async def dispatch(self, request: Request, call_next):
        redis = await self._get_redis()

        ip = request.client.host if request.client else "unknown"
        user_id = self._get_user_id_from_jwt(request)
        if user_id is None:
            user_id = ip
            limits = DEFAULT_PLAN_LIMITS["demo"]
            plan_name = "demo"
        else:
            limits = await self._get_plan_limits(user_id)
            plan_name = limits.get("name", "demo")

        endpoint = request.url.path
        key = f"rate:{user_id}:{endpoint}"
        max_requests = limits.get("max_requests", 5)
        window_seconds = limits.get("window_seconds", 60)

        try:
            current = await redis.eval(LUA_RATE_LIMIT, 1, key, window_seconds)
            if current > max_requests:
                ttl = await redis.ttl(key)
                ttl = max(ttl or 0, 0)
                RATE_LIMIT_HITS.labels(str(user_id), plan_name, endpoint, ip).inc()

                return JSONResponse(
                    status_code=HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "detail": "Demasiadas solicitudes. Intenta de nuevo más tarde.",
                        "retry_after": ttl
                    }
                )
        except Exception as e:
            # Fail-open: permitir request si Redis falla
            logger.error({"event": "redis_error", "user_id": user_id, "endpoint": endpoint, "error": str(e)})
            return await call_next(request)

        # Registrar request total
        REQUESTS_TOTAL.labels(str(user_id), plan_name, endpoint, ip).inc()

        return await call_next(request)

    async def __del__(self):
        if self.redis:
            await self.redis.close()
