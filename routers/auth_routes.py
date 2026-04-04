
import os
import logging
import re
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field, field_validator, AliasChoices
from typing import Optional

from services.auth_service import (
    oauth_login_or_register,
    refresh_access_token_service,
    register_email_password_service,
    login_email_password_service,
)
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
logger.propagate = False

# ---------------- Configuración General ----------------
RATE_LIMIT_REQUESTS = 5
RATE_LIMIT_PERIOD = 10  # segundos
JWT_SECRET = os.getenv("JWT_SECRET_KEY", os.getenv("JWT_SECRET", "default_secret"))
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


def _debug_enabled() -> bool:
    try:
        from config import DEBUG as CONFIG_DEBUG

        return bool(CONFIG_DEBUG)
    except Exception:
        return str(os.getenv("DEBUG") or "").strip() in {"1", "true", "True"}

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


class RegisterSchema(BaseModel):
    email: str = Field(..., min_length=5, max_length=100)
    password: str = Field(..., min_length=8, max_length=200)
    full_name: Optional[str] = Field(None, min_length=1, max_length=120)

    @field_validator("email")
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("Email inválido")
        return v

class LoginSchema(BaseModel):
    email: str = Field(..., min_length=5, max_length=100)
    password: str = Field(..., min_length=8, max_length=200)

    @field_validator("email")
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("Email inválido")
        return v

class RefreshSchema(BaseModel):
    """Schema estricto para refresh que acepta variantes mediante AliasChoices"""
    refresh_token: str = Field(
        ...,
        validation_alias=AliasChoices(
            "refresh_token", "refreshToken", "token", "access_token", "refresh"
        ),
        min_length=10,
        max_length=5000,
        description="El token de refresco a validar"
    )

# ---------------- Seguridad Input ----------------
def sanitize_input(value: str) -> str:
    if re.search(r"[;$<>]", value):
        raise HTTPException(status_code=400, detail="Entrada inválida detectada")
    return value

@router.post("/oauth")
async def oauth_login(
    data: OAuthSchema,
    request: Request,
) -> dict:
    logger.info(f'{{"event": "oauth_login_attempt", "provider": "{data.provider}", "ip": "{request.client.host}"}}')
    env = os.getenv("ENVIRONMENT", "production").lower()
    oauth_enabled = str(os.getenv("OAUTH_ENABLED") or "").strip().lower() in {"1", "true", "t", "yes"}
    if env == "production" and not oauth_enabled:
        raise HTTPException(status_code=503, detail="oauth_disabled")

    if data.provider == "google":
        if not os.getenv("GOOGLE_CLIENT_ID") or not os.getenv("GOOGLE_CLIENT_SECRET"):
            raise HTTPException(status_code=503, detail="oauth_google_not_configured")
    if data.provider == "apple":
        if not os.getenv("APPLE_CLIENT_ID") or not os.getenv("APPLE_CLIENT_SECRET"):
            raise HTTPException(status_code=503, detail="oauth_apple_not_configured")
    try:
        provider = sanitize_input(data.provider)
        id_token = sanitize_input(data.id_token)
        name = sanitize_input(data.name) if data.name else None

        # Usar Circuit Breaker para proteger contra saturación
        result = await cb_oauth.call(oauth_login_or_register, None, provider, id_token, name)
        logger.info(f'{{"event": "oauth_login_success", "provider": "{provider}", "ip": "{request.client.host}"}}')
        return result
    except RuntimeError as e:
        if "Circuit breaker" in str(e):
            logger.warning(f'{{"event": "oauth_circuit_open", "provider": "{data.provider}", "ip": "{request.client.host}"}}')
            raise HTTPException(status_code=503, detail="oauth_service_temporarily_unavailable")
        raise
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
        # El token ya viene validado estrictamente por Pydantic (AliasChoices y min_length)
        refresh_token = sanitize_input(data.refresh_token.strip())
        
        # Usar Circuit Breaker para proteger contra saturación
        result = await cb_refresh.call(refresh_access_token_service, refresh_token)
        logger.info(f'{{"event": "refresh_token_success", "ip": "{request.client.host}"}}')
        return result
    except RuntimeError as e:
        if "Circuit breaker" in str(e):
            logger.warning(f'{{"event": "refresh_circuit_open", "ip": "{request.client.host}"}}')
            raise HTTPException(status_code=503, detail="token_refresh_temporarily_unavailable")
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'{{"event": "refresh_token_error", "error": "{str(e)}"}}', exc_info=True)
        raise HTTPException(status_code=400, detail="Error al refrescar token")


@router.post("/register")
async def register_route(
    data: RegisterSchema,
    request: Request,
) -> dict:
    # Safe slicing para evitar IndexError con emails cortos
    email_preview = data.email[:3] + "..." + data.email[-6:] if len(data.email) > 9 else data.email[:3] + "..."
    logger.info(f'{{"event": "register_attempt", "ip": "{request.client.host}", "email_preview": "{email_preview}"}}')
    try:
        email = sanitize_input(data.email)
        password = data.password
        full_name = sanitize_input(data.full_name) if data.full_name else None

        result = await register_email_password_service(
            email=email,
            password=password,
            full_name=full_name,
            session=None,
        )
        logger.info(f'{{"event": "register_success", "ip": "{request.client.host}"}}')
        return result
    except Exception as e:
        error_str = str(e)
        logger.error(f'{{"event": "register_error", "error": "{error_str}", "ip": "{request.client.host}"}}')
        # Log más detallado para debuggear 422
        import traceback
        logger.error(f'Register traceback: {traceback.format_exc()}')
        detail = (error_str or "Error al registrar") if _debug_enabled() else "register_failed"
        raise HTTPException(status_code=400, detail=detail)


@router.post("/login")
async def login_route(
    data: LoginSchema,
    request: Request,
) -> dict:
    logger.info(f'{{"event": "login_attempt", "ip": "{request.client.host}"}}')
    try:
        email = sanitize_input(data.email)
        password = data.password
        result = await login_email_password_service(
            email=email,
            password=password,
            session=None,
        )
        logger.info(f'{{"event": "login_success", "ip": "{request.client.host}"}}')
        return result
    except Exception as e:
        logger.error(f'{{"event": "login_error", "error": "{str(e)}"}}', exc_info=True)
        detail = (str(e) or "Error al iniciar sesión") if _debug_enabled() else "login_failed"
        raise HTTPException(status_code=400, detail=detail)
