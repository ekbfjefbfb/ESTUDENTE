# middlewares/timeout_middleware_saas.py
import os
import asyncio
import logging
from fastapi import Request, WebSocket, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from jose import jwt
from sqlalchemy.future import select
from database.db_enterprise import get_primary_session as get_async_db
from models.models import User
from utils.metrics import REQUESTS_TOTAL, TIMEOUT_COUNT

logger = logging.getLogger("timeout_middleware")

# ---------------- Timeout base ----------------
BASE_TIMEOUT_MAP = {
    "/health": 5.0,
    "/auth": 5.0,
    "/assistant": 30.0,
    "/vision": 30.0,
    "/api/unified-chat": 60.0,
    "/unified-chat": 60.0,
    "/documents": 45.0,
}
DEFAULT_TIMEOUT = 15.0

# Multiplicador por plan
PLAN_TIMEOUT_MULTIPLIER = {
    "demo": 1.0,
    "basic": 1.5,
    "pro": 2.0
}


class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    Middleware de timeout dinámico por endpoint y plan de usuario.
    Usa métricas centralizadas para Prometheus.
    """

    async def _get_user_id_from_jwt(self, request: Request):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
        token = auth_header.split(" ")[1]
        try:
            # Sintonizado con sub (string) para evitar errores de conversión a int
            payload = jwt.decode(
                token,
                os.getenv("JWT_SECRET_KEY", os.getenv("JWT_SECRET")),
                algorithms=["HS256"],
            )
            return payload.get("sub")
        except Exception:
            return None

    async def _get_user_plan_multiplier(self, user_id):
        if not user_id:
            return PLAN_TIMEOUT_MULTIPLIER["demo"]
        try:
            from sqlalchemy import text
            session = await get_async_db()
            async with session:
                result = await session.execute(
                    text("SELECT id FROM users WHERE id = :user_id"),
                    {"user_id": user_id}
                )
                row = result.first()
                if row:
                    return PLAN_TIMEOUT_MULTIPLIER["demo"]
        except Exception as e:
            logger.warning(f"Error fetching plan multiplier: {e}")
            return PLAN_TIMEOUT_MULTIPLIER["demo"]
        return PLAN_TIMEOUT_MULTIPLIER["demo"]

    def _get_base_timeout(self, path: str):
        # Render/Proxy deployments usually mount the API under '/api'.
        # Normalize so our prefix map matches consistently.
        if path.startswith("/api/"):
            path = path[4:]
        for prefix, t in BASE_TIMEOUT_MAP.items():
            if path.startswith(prefix):
                return t
        return DEFAULT_TIMEOUT

    async def dispatch(self, request: Request, call_next):
        # Ignorar WebSockets
        if isinstance(request, WebSocket):
            return await call_next(request)

        user_id = await self._get_user_id_from_jwt(request)
        plan_multiplier = await self._get_user_plan_multiplier(user_id)
        timeout = self._get_base_timeout(request.url.path) * plan_multiplier

        # NOTE: REQUESTS_TOTAL se trackea en RateLimitMiddleware — no duplicar aquí

        try:
            response = await asyncio.wait_for(call_next(request), timeout=timeout)
            return response
        except asyncio.TimeoutError:
            try:
                TIMEOUT_COUNT.labels(endpoint=request.url.path, method=request.method).inc()
            except Exception:
                pass
            raise HTTPException(
                status_code=504,
                detail=f"Timeout: la solicitud excedió los {timeout:.2f}s de espera"
            )
