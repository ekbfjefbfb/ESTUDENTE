
import os
import logging
import re
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from jose import jwt, JWTError

from database.db_enterprise import get_primary_session as get_async_db
from services.auth_service import oauth_login_or_register, refresh_access_token_service
from utils.resilience import CircuitBreaker

# ---------------- Logger Config ----------------
router = APIRouter()
logger = logging.getLogger("auth_routes")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '{"time": "%(asctime)s", "level": "%(levelname)s", "message": %(message)s}'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

# ---------------- Configuración General ----------------
RATE_LIMIT_REQUESTS = 5
RATE_LIMIT_PERIOD = 10  # segundos
JWT_SECRET = os.getenv("JWT_SECRET_KEY", os.getenv("JWT_SECRET", "default_secret"))
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# ---------------- Circuit Breakers ----------------
cb_oauth = CircuitBreaker("oauth_call", max_failures=3, reset_timeout=30)
cb_refresh = CircuitBreaker("refresh_call", max_failures=3, reset_timeout=30)

# ---------------- Schemas ----------------
class OAuthSchema(BaseModel):
    provider: str = Field(..., pattern="^(google|apple)$", description="Proveedor: google o apple")
    id_token: str = Field(..., min_length=10, max_length=2000, description="ID token JWT del proveedor")
    name: Optional[str] = Field(None, min_length=1, max_length=120, description="Nombre opcional del usuario")

    @field_validator("id_token")
    def validate_id_token_format(cls, v: str) -> str:
        if len(v.split(".")) != 3:
            raise ValueError("Formato de ID token inválido")
        return v


class RefreshSchema(BaseModel):
    refresh_token: str = Field(..., min_length=10, max_length=2000, description="Refresh token JWT")

    @field_validator("refresh_token")
    def validate_jwt(cls, v: str) -> str:
        try:
            jwt.decode(v, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except JWTError:
            raise ValueError("Token inválido o expirado")
        return v

# ---------------- Seguridad Input ----------------
def sanitize_input(value: str) -> str:
    if re.search(r"[;$<>]", value):
        raise HTTPException(status_code=400, detail="Entrada inválida detectada")
    return value

@router.post("/oauth")
async def oauth_login(
    data: OAuthSchema,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    logger.info(f'{{"event": "oauth_login_attempt", "provider": "{data.provider}", "ip": "{request.client.host}"}}')
    try:
        provider = sanitize_input(data.provider)
        id_token = sanitize_input(data.id_token)
        name = sanitize_input(data.name) if data.name else None

        result = await oauth_login_or_register(db, provider, id_token, name)
        logger.info(f'{{"event": "oauth_login_success", "provider": "{provider}", "ip": "{request.client.host}"}}')
        return result
    except Exception as e:
        logger.error(f'{{"event": "oauth_login_error", "error": "{str(e)}"}}', exc_info=True)
        raise HTTPException(status_code=400, detail="Error al procesar login OAuth")


@router.post("/refresh")
async def refresh_token_route(
    data: RefreshSchema,
    request: Request,
) -> dict:
    logger.info(f'{{"event": "refresh_token_attempt", "ip": "{request.client.host}"}}')
    try:
        refresh_token = sanitize_input(data.refresh_token)
        result = await refresh_access_token_service(refresh_token)
        logger.info(f'{{"event": "refresh_token_success", "ip": "{request.client.host}"}}')
        return result
    except Exception as e:
        logger.error(f'{{"event": "refresh_token_error", "error": "{str(e)}"}}', exc_info=True)
        raise HTTPException(status_code=400, detail="Error al refrescar token")
