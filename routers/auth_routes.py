
import os
import logging
import re
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field, field_validator, AliasChoices
from typing import Optional

from services.auth_service import (
    complete_google_oauth_login,
    oauth_login_or_register,
    refresh_access_token_service,
    register_email_password_service,
    login_email_password_service,
)
from services.google_workspace.google_auth_service import google_auth_service
from utils.resilience import CircuitBreaker
from config import (
    APPLE_CLIENT_ID,
    APPLE_CLIENT_SECRET,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_OAUTH_AUTHORIZE_PATH,
    GOOGLE_OAUTH_CALLBACK_PATH,
    GOOGLE_OAUTH_EXCHANGE_PATH,
    OAUTH_ENABLED,
)

# ---------------- Logger Config ----------------
router = APIRouter()
logger = logging.getLogger("auth_routes")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}'
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


class GoogleOAuthCodeSchema(BaseModel):
    code: str = Field(
        ...,
        validation_alias=AliasChoices("code", "authorization_code", "authorizationCode"),
        min_length=8,
        max_length=4000,
    )
    state: str = Field(..., min_length=8, max_length=512)


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


def _request_base_url(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}".rstrip("/")
    return str(request.base_url).rstrip("/")


def _client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@router.get("/google/config")
async def google_oauth_config(request: Request) -> dict:
    base_url = _request_base_url(request)
    config = google_auth_service.get_public_config()
    return {
        "success": True,
        "provider": "google",
        **config,
        "authorization_endpoint": f"{base_url}{GOOGLE_OAUTH_AUTHORIZE_PATH}",
        "exchange_code_endpoint": f"{base_url}{GOOGLE_OAUTH_EXCHANGE_PATH}",
        "callback_endpoint": f"{base_url}{GOOGLE_OAUTH_CALLBACK_PATH}",
    }


@router.get("/google/authorize-url")
async def google_authorize_url(request: Request, state: Optional[str] = None) -> dict:
    logger.info(f'{{"event": "google_oauth_authorize_attempt", "ip": "{_client_ip(request)}"}}')
    try:
        authorization_url, resolved_state = await google_auth_service.create_authorization_url(state=state)
        config = google_auth_service.get_public_config()
        return {
            "success": True,
            "provider": "google",
            "authorization_url": authorization_url,
            "state": resolved_state,
            "redirect_uri": config.get("redirect_uri"),
            "scopes": config.get("scopes", []),
        }
    except Exception as e:
        logger.error(f'{{"event": "google_oauth_authorize_error", "error": "{str(e)}"}}', exc_info=True)
        raise HTTPException(status_code=503, detail=str(e) or "google_oauth_authorize_failed")


@router.post("/google/exchange-code")
async def google_exchange_code(data: GoogleOAuthCodeSchema, request: Request) -> dict:
    logger.info(f'{{"event": "google_oauth_exchange_attempt", "ip": "{_client_ip(request)}"}}')
    try:
        return await complete_google_oauth_login(code=sanitize_input(data.code), state=sanitize_input(data.state))
    except Exception as e:
        logger.error(f'{{"event": "google_oauth_exchange_error", "error": "{str(e)}"}}', exc_info=True)
        raise HTTPException(status_code=400, detail=str(e) or "google_oauth_exchange_failed")


@router.get("/google/callback")
async def google_callback(code: str, state: str, request: Request) -> dict:
    logger.info(f'{{"event": "google_oauth_callback_attempt", "ip": "{_client_ip(request)}"}}')
    if len(str(code or "").strip()) < 8 or len(str(state or "").strip()) < 8:
        raise HTTPException(status_code=400, detail="invalid_google_oauth_callback_params")
    try:
        return await complete_google_oauth_login(code=sanitize_input(code), state=sanitize_input(state))
    except Exception as e:
        logger.error(f'{{"event": "google_oauth_callback_error", "error": "{str(e)}"}}', exc_info=True)
        raise HTTPException(status_code=400, detail=str(e) or "google_oauth_callback_failed")

@router.post("/oauth")
async def oauth_login(
    data: OAuthSchema,
    request: Request,
) -> dict:
    logger.info(f'{{"event": "oauth_login_attempt", "provider": "{data.provider}", "ip": "{_client_ip(request)}"}}')
    env = os.getenv("ENVIRONMENT", "production").lower()
    if env == "production" and not OAUTH_ENABLED:
        raise HTTPException(status_code=503, detail="oauth_disabled")

    if data.provider == "google":
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            raise HTTPException(status_code=503, detail="oauth_google_not_configured")
    if data.provider == "apple":
        if not APPLE_CLIENT_ID or not APPLE_CLIENT_SECRET:
            raise HTTPException(status_code=503, detail="oauth_apple_not_configured")
    try:
        provider = sanitize_input(data.provider)
        id_token = sanitize_input(data.id_token)
        name = sanitize_input(data.name) if data.name else None

        # Usar Circuit Breaker para proteger contra saturación
        result = await cb_oauth.call(oauth_login_or_register, None, provider, id_token, name)
        logger.info(f'{{"event": "oauth_login_success", "provider": "{provider}", "ip": "{_client_ip(request)}"}}')
        return result
    except RuntimeError as e:
        if "Circuit breaker" in str(e):
            logger.warning(f'{{"event": "oauth_circuit_open", "provider": "{data.provider}", "ip": "{_client_ip(request)}"}}')
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
    logger.info(f'{{"event": "refresh_token_attempt", "ip": "{_client_ip(request)}"}}')
    try:
        # El token ya viene validado estrictamente por Pydantic (AliasChoices y min_length)
        refresh_token = sanitize_input(data.refresh_token.strip())
        
        # Usar Circuit Breaker para proteger contra saturación
        result = await cb_refresh.call(refresh_access_token_service, refresh_token)
        logger.info(f'{{"event": "refresh_token_success", "ip": "{_client_ip(request)}"}}')
        return result
    except RuntimeError as e:
        if "Circuit breaker" in str(e):
            logger.warning(f'{{"event": "refresh_circuit_open", "ip": "{_client_ip(request)}"}}')
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
    logger.info(f'{{"event": "register_attempt", "ip": "{_client_ip(request)}", "email_preview": "{email_preview}"}}')
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
        logger.info(f'{{"event": "register_success", "ip": "{_client_ip(request)}"}}')
        return result
    except Exception as e:
        error_str = str(e)
        logger.error(f'{{"event": "register_error", "error": "{error_str}", "ip": "{_client_ip(request)}"}}')
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
    logger.info(f'{{"event": "login_attempt", "ip": "{_client_ip(request)}"}}')
    try:
        email = sanitize_input(data.email)
        password = data.password
        result = await login_email_password_service(
            email=email,
            password=password,
            session=None,
        )
        logger.info(f'{{"event": "login_success", "ip": "{_client_ip(request)}"}}')
        return result
    except Exception as e:
        logger.error(f'{{"event": "login_error", "error": "{str(e)}"}}', exc_info=True)
        detail = (str(e) or "Error al iniciar sesión") if _debug_enabled() else "login_failed"
        raise HTTPException(status_code=400, detail=detail)
