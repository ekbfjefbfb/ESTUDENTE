import logging
from fastapi import HTTPException, Request
from starlette.status import HTTP_429_TOO_MANY_REQUESTS
from prometheus_client import Counter
from services.redis_service import get_redis_client

# ---------------- Logging ----------------
logger = logging.getLogger("rate_limit")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel("INFO")

# ---------------- Metrics ----------------
RATE_LIMIT_EXCEEDED = Counter(
    "rate_limit_exceeded_total",
    "Número de requests bloqueadas por rate limit",
    ["key", "user_id", "ip", "task_type"]
)

# ---------------- LUA Script para atomicidad ----------------
LUA_RATE_LIMIT = """
local current = redis.call("INCR", KEYS[1])
if current == 1 then
    redis.call("PEXPIRE", KEYS[1], ARGV[1])
end
return current
"""

# ---------------- Función principal ----------------
async def rate_limit(
    key: str,
    max_calls: int,
    period_seconds: int,
    user_id: str | None = None,
    ip: str | None = None,
    task_type: str | None = None,
    raise_on_exceed: bool = True,
    fail_open: bool = True
) -> bool:
    """
    Rate limiter avanzado basado en Redis.
    Incluye soporte por usuario, IP y tipo de tarea.
    Retorna True si la request está permitida, False si no (solo si raise_on_exceed=False).
    
    Parámetros:
      - key: str -> identificador general para el rate limit
      - user_id: str -> opcional, ID del usuario autenticado
      - ip: str -> opcional, IP del cliente
      - task_type: str -> opcional, tipo de tarea (chat, ocr, generate_image, etc.)
      - max_calls: int -> número máximo de llamadas permitidas en el período
      - period_seconds: int -> duración del período en segundos
      - raise_on_exceed: bool -> si True, lanza HTTPException al exceder
      - fail_open: bool -> si True, permite requests cuando Redis falla
    """
    try:
        r = await get_redis_client()
        if r is None:
            msg = f"[rate_limit] Redis no disponible para {key}"
            logger.warning(msg)
            if fail_open:
                return True
            raise HTTPException(status_code=500, detail=msg)

        # Crear clave más granular (ej: rate:user:123:chat)
        composite_key = f"rate:{key}"
        if user_id:
            composite_key += f":user:{user_id}"
        if ip:
            composite_key += f":ip:{ip}"
        if task_type:
            composite_key += f":task:{task_type}"

        period_ms = int(period_seconds * 1000)
        count = await r.eval(LUA_RATE_LIMIT, 1, composite_key, period_ms)
        allowed = count <= max_calls

        if not allowed:
            RATE_LIMIT_EXCEEDED.labels(
                key=key,
                user_id=user_id or "anonymous",
                ip=ip or "unknown",
                task_type=task_type or "generic"
            ).inc()

            retry_after = period_seconds
            try:
                ttl_ms = await r.pttl(composite_key)
                if ttl_ms and ttl_ms > 0:
                    retry_after = round(ttl_ms / 1000, 2)
            except Exception:
                pass

            msg = (
                f"Rate limit exceeded for {composite_key}: "
                f"{count}/{max_calls} in {period_seconds}s"
            )
            logger.warning({
                "event": "rate_limited",
                "key": composite_key,
                "user_id": user_id,
                "ip": ip,
                "task_type": task_type,
                "count": count,
                "max_calls": max_calls,
                "period_s": period_seconds,
                "retry_after": retry_after
            })

            if raise_on_exceed:
                headers = {"Retry-After": str(retry_after)}
                raise HTTPException(
                    status_code=HTTP_429_TOO_MANY_REQUESTS,
                    detail=msg,
                    headers=headers
                )
            else:
                return False

        return True

    except HTTPException:
        raise
    except Exception as e:
        logger.error({
            "event": "rate_limit_redis_error",
            "key": key,
            "user_id": user_id,
            "ip": ip,
            "task_type": task_type,
            "error": str(e)
        }, exc_info=True)
        return fail_open


# ---------------- Helper (extra opcional) ----------------
async def rate_limit_request(request: Request, key: str, max_calls: int, period_seconds: int, task_type: str):
    """Helper para usar dentro de middlewares o routers."""
    ip = request.client.host if request.client else None
    user_id = getattr(request.state, "user_id", None)
    return await rate_limit(
        key=key,
        max_calls=max_calls,
        period_seconds=period_seconds,
        user_id=user_id,
        ip=ip,
        task_type=task_type
    )
