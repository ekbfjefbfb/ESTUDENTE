# middlewares/timeout_middleware_saas.py
import os
import asyncio
from fastapi import Request, WebSocket, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from jose import jwt
from sqlalchemy.future import select
from database.db_enterprise import get_primary_session as get_async_db
from models.models import User
from utils.metrics import REQUESTS_TOTAL, TIMEOUT_COUNT

# ---------------- Timeout base ----------------
BASE_TIMEOUT_MAP = {
    "/health": 5.0,
    "/auth": 5.0,
    "/assistant": 30.0,
    "/vision": 30.0,
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
            payload = jwt.decode(
                token,
                os.getenv("JWT_SECRET_KEY", os.getenv("JWT_SECRET")),
                algorithms=["HS256"],
            )
            return int(payload.get("user_id"))
        except Exception:
            return None

    async def _get_user_plan_multiplier(self, user_id):
        if not user_id:
            return PLAN_TIMEOUT_MULTIPLIER["demo"]
        try:
            async with get_async_db() as db:
                result = await db.execute(select(User).where(User.id == user_id))
                user: User = result.scalar_one_or_none()
                if user and user.plan:
                    return PLAN_TIMEOUT_MULTIPLIER.get(user.plan.name.lower(), 1.0)
        except Exception:
            return PLAN_TIMEOUT_MULTIPLIER["demo"]
        return PLAN_TIMEOUT_MULTIPLIER["demo"]

    def _get_base_timeout(self, path: str):
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
        user_key = user_id or request.client.host

        # Incrementa la métrica centralizada de requests
        REQUESTS_TOTAL.labels(
            user_id=str(user_key),
            plan=str(plan_multiplier),
            endpoint=request.url.path
        ).inc()

        try:
            return await asyncio.wait_for(call_next(request), timeout=timeout)
        except asyncio.TimeoutError:
            TIMEOUT_COUNT.labels(
                user_id=str(user_key),
                plan=str(plan_multiplier),
                endpoint=request.url.path
            ).inc()
            raise HTTPException(
                status_code=504,
                detail=f"Timeout: la solicitud excedió los {timeout:.2f}s de espera"
            )
