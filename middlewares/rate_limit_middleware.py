import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from jose import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

from utils.metrics import REQUESTS_TOTAL, RATE_LIMIT_HITS
from utils.rate_limit import (
    RateLimitDecision,
    RateLimitRule,
    build_rate_limit_headers,
    evaluate_rate_limits,
)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        if isinstance(record.msg, dict):
            record.msg = json.dumps(record.msg)
        return super().format(record)


logger = logging.getLogger("rate_limit_middleware")
if not logger.handlers:
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)

JWT_SECRET = os.getenv("JWT_SECRET_KEY", os.getenv("JWT_SECRET", "default-jwt-secret-change-in-production"))
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
BYPASS_METHODS = frozenset({"OPTIONS", "HEAD"})
PUBLIC_PATHS = {
    "/",
    "/health",
    "/api/health",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/csrf-token",
    "/api/unified-chat/health",
    "/api/unified-chat/info",
    "/unified-chat/health",
    "/unified-chat/info",
}


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class EndpointPolicy:
    name: str
    prefixes: tuple[str, ...]
    methods: frozenset[str]
    rules: tuple[RateLimitRule, ...]


POLICIES = (
    EndpointPolicy(
        name="auth",
        prefixes=(
            "/api/auth/login",
            "/api/auth/register",
            "/api/auth/refresh",
            "/api/auth/oauth",
        ),
        methods=frozenset({"POST"}),
        rules=(
            RateLimitRule(
                name="auth_ip",
                scope="ip",
                max_requests=_env_int("RATE_LIMIT_AUTH_IP_MAX_REQUESTS", 10),
                window_seconds=_env_int("RATE_LIMIT_AUTH_IP_WINDOW_SECONDS", 60),
                block_seconds=_env_int("RATE_LIMIT_AUTH_IP_BLOCK_SECONDS", 300),
            ),
        ),
    ),
    EndpointPolicy(
        name="chat_http",
        prefixes=(
            "/api/unified-chat/message",
            "/api/unified-chat/message/json",
            "/api/unified-chat/stt",
            "/api/unified-chat/tts",
            "/api/unified-chat/voice/message",
            "/unified-chat/message",
            "/unified-chat/message/json",
            "/unified-chat/stt",
            "/unified-chat/tts",
            "/unified-chat/voice/message",
        ),
        methods=frozenset({"POST"}),
        rules=(
            RateLimitRule(
                name="chat_ip",
                scope="ip",
                max_requests=_env_int("RATE_LIMIT_CHAT_IP_MAX_REQUESTS", 120),
                window_seconds=_env_int("RATE_LIMIT_CHAT_IP_WINDOW_SECONDS", 60),
                block_seconds=_env_int("RATE_LIMIT_CHAT_IP_BLOCK_SECONDS", 120),
            ),
            RateLimitRule(
                name="chat_user",
                scope="user",
                max_requests=_env_int("RATE_LIMIT_CHAT_USER_MAX_REQUESTS", 40),
                window_seconds=_env_int("RATE_LIMIT_CHAT_USER_WINDOW_SECONDS", 60),
                block_seconds=_env_int("RATE_LIMIT_CHAT_USER_BLOCK_SECONDS", 120),
            ),
        ),
    ),
    EndpointPolicy(
        name="ai_processing",
        prefixes=(
            "/api/images/analyze",
            "/api/documents/analyze",
            "/api/documents/generate",
            "/api/recordings/",
            "/api/scheduled-recordings/",
            "/api/voice-notes/",
        ),
        methods=MUTATING_METHODS,
        rules=(
            RateLimitRule(
                name="ai_processing_ip",
                scope="ip",
                max_requests=_env_int("RATE_LIMIT_AI_IP_MAX_REQUESTS", 60),
                window_seconds=_env_int("RATE_LIMIT_AI_IP_WINDOW_SECONDS", 60),
                block_seconds=_env_int("RATE_LIMIT_AI_IP_BLOCK_SECONDS", 180),
            ),
            RateLimitRule(
                name="ai_processing_user",
                scope="user",
                max_requests=_env_int("RATE_LIMIT_AI_USER_MAX_REQUESTS", 20),
                window_seconds=_env_int("RATE_LIMIT_AI_USER_WINDOW_SECONDS", 60),
                block_seconds=_env_int("RATE_LIMIT_AI_USER_BLOCK_SECONDS", 180),
            ),
        ),
    ),
    EndpointPolicy(
        name="mutating_api",
        prefixes=("/api/",),
        methods=MUTATING_METHODS,
        rules=(
            RateLimitRule(
                name="mutating_ip",
                scope="ip",
                max_requests=_env_int("RATE_LIMIT_MUTATING_IP_MAX_REQUESTS", 240),
                window_seconds=_env_int("RATE_LIMIT_MUTATING_IP_WINDOW_SECONDS", 60),
                block_seconds=_env_int("RATE_LIMIT_MUTATING_IP_BLOCK_SECONDS", 60),
            ),
            RateLimitRule(
                name="mutating_user",
                scope="user",
                max_requests=_env_int("RATE_LIMIT_MUTATING_USER_MAX_REQUESTS", 120),
                window_seconds=_env_int("RATE_LIMIT_MUTATING_USER_WINDOW_SECONDS", 60),
                block_seconds=_env_int("RATE_LIMIT_MUTATING_USER_BLOCK_SECONDS", 60),
            ),
        ),
    ),
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def _client_ip(self, request: Request) -> str:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        if request.client and request.client.host:
            return request.client.host
        return "unknown"

    def _extract_user_id(self, request: Request) -> Optional[str]:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
        if not JWT_SECRET:
            return None
        token = auth_header.split(" ", 1)[1].strip()
        if not token:
            return None
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except Exception:
            return None
        subject = payload.get("sub")
        return str(subject) if subject else None

    def _is_public_path(self, path: str) -> bool:
        if path in PUBLIC_PATHS:
            return True
        return path.startswith("/docs/") or path.startswith("/redoc/")

    def _match_policy(self, path: str, method: str) -> Optional[EndpointPolicy]:
        for policy in POLICIES:
            if method not in policy.methods:
                continue
            if any(path.startswith(prefix) for prefix in policy.prefixes):
                return policy
        return None

    def _pick_header_decision(self, decisions: list[RateLimitDecision]) -> Optional[RateLimitDecision]:
        eligible = [decision for decision in decisions if decision.identifier]
        if not eligible:
            return None
        return min(
            eligible,
            key=lambda decision: (
                decision.remaining / max(decision.limit, 1),
                decision.remaining,
                decision.retry_after,
            ),
        )

    def _record_metric(self, request: Request, status_code: int, user_type: str) -> None:
        try:
            REQUESTS_TOTAL.labels(
                method=request.method,
                endpoint=request.url.path,
                status_code=str(status_code),
                user_type=user_type,
            ).inc()
        except Exception:
            pass

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method.upper()

        if method in BYPASS_METHODS or self._is_public_path(path):
            response = await call_next(request)
            self._record_metric(request, getattr(response, "status_code", 200), "public")
            return response

        policy = self._match_policy(path, method)
        user_id = self._extract_user_id(request)
        ip_address = self._client_ip(request)

        if policy is not None:
            try:
                decisions = await evaluate_rate_limits(
                    namespace=policy.name,
                    identifiers={"ip": ip_address, "user": user_id},
                    rules=policy.rules,
                )
                blocked = next((decision for decision in decisions if not decision.allowed), None)
                if blocked is not None:
                    try:
                        RATE_LIMIT_HITS.labels(endpoint=path, user_type=blocked.scope).inc()
                    except Exception:
                        pass
                    self._record_metric(request, HTTP_429_TOO_MANY_REQUESTS, blocked.scope)
                    logger.warning(
                        {
                            "event": "rate_limited_request",
                            "path": path,
                            "method": method,
                            "policy": policy.name,
                            "scope": blocked.scope,
                            "rule": blocked.rule_name,
                            "retry_after": blocked.retry_after,
                            "ip": ip_address,
                            "user_id": user_id,
                            "backend": blocked.backend,
                        }
                    )
                    return JSONResponse(
                        status_code=HTTP_429_TOO_MANY_REQUESTS,
                        headers=build_rate_limit_headers(blocked),
                        content={
                            "detail": "Demasiadas solicitudes. Intenta nuevamente más tarde.",
                            "policy": policy.name,
                            "scope": blocked.scope,
                            "rule": blocked.rule_name,
                            "retry_after": blocked.retry_after,
                            "blocked": blocked.blocked,
                        },
                    )
            except Exception as exc:
                logger.error(
                    {
                        "event": "rate_limit_middleware_error",
                        "path": path,
                        "method": method,
                        "ip": ip_address,
                        "user_id": user_id,
                        "error": str(exc),
                    },
                    exc_info=True,
                )
                decisions = []
        else:
            decisions = []

        response = await call_next(request)
        header_decision = self._pick_header_decision(decisions)
        if header_decision is not None:
            for key, value in build_rate_limit_headers(header_decision).items():
                response.headers[key] = value
            response.headers["X-RateLimit-Backend"] = header_decision.backend

        self._record_metric(
            request,
            getattr(response, "status_code", 200),
            "authenticated" if user_id else "anonymous",
        )
        return response
