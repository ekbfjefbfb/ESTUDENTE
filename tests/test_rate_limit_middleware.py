import asyncio
import importlib

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from jose import jwt

import middlewares.rate_limit_middleware as rate_limit_middleware
from middlewares.rate_limit_middleware import EndpointPolicy, RateLimitMiddleware
from utils.rate_limit import RateLimitRule

rate_limit_utils = importlib.import_module("utils.rate_limit")


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.post("/api/auth/login")
    async def login():
        return {"ok": True}

    @app.post("/api/unified-chat/message")
    async def chat_message():
        return {"ok": True}

    @app.get("/api/health")
    async def health():
        return {"ok": True}

    @app.exception_handler(429)
    async def handle_rate_limit(_, exc):
        return JSONResponse(status_code=429, content={"detail": str(exc.detail)})

    return app


def _token_for(user_id: str) -> str:
    return jwt.encode({"sub": user_id}, rate_limit_middleware.JWT_SECRET, algorithm=rate_limit_middleware.JWT_ALGORITHM)


@pytest.fixture(autouse=True)
def force_memory_rate_limit_backend(monkeypatch: pytest.MonkeyPatch):
    async def _fake_get_redis_client():
        return None

    monkeypatch.setattr(rate_limit_utils, "get_redis_client", _fake_get_redis_client)


@pytest_asyncio.fixture
async def async_client_factory():
    clients: list[httpx.AsyncClient] = []

    async def _factory(app: FastAPI) -> httpx.AsyncClient:
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )
        clients.append(client)
        return client

    try:
        yield _factory
    finally:
        for client in clients:
            await client.aclose()


@pytest.mark.asyncio
async def test_rate_limit_auth_blocks_by_ip(
    monkeypatch: pytest.MonkeyPatch,
    async_client_factory,
):
    policy = EndpointPolicy(
        name="test-auth-ip",
        prefixes=("/api/auth/login",),
        methods=frozenset({"POST"}),
        rules=(
            RateLimitRule(
                name="test_auth_ip",
                scope="ip",
                max_requests=2,
                window_seconds=60,
                block_seconds=30,
            ),
        ),
    )
    monkeypatch.setattr(rate_limit_middleware, "POLICIES", (policy,))

    app = _build_app()
    client = await async_client_factory(app)
    headers = {"X-Forwarded-For": "203.0.113.10"}
    assert (await client.post("/api/auth/login", headers=headers)).status_code == 200
    assert (await client.post("/api/auth/login", headers=headers)).status_code == 200

    blocked = await client.post("/api/auth/login", headers=headers)
    assert blocked.status_code == 429
    assert blocked.json()["scope"] == "ip"
    assert int(blocked.headers["Retry-After"]) >= 1


@pytest.mark.asyncio
async def test_rate_limit_chat_blocks_per_user_but_not_other_users(
    monkeypatch: pytest.MonkeyPatch,
    async_client_factory,
):
    policy = EndpointPolicy(
        name="test-chat-user",
        prefixes=("/api/unified-chat/message",),
        methods=frozenset({"POST"}),
        rules=(
            RateLimitRule(
                name="test_chat_ip",
                scope="ip",
                max_requests=100,
                window_seconds=60,
                block_seconds=30,
            ),
            RateLimitRule(
                name="test_chat_user",
                scope="user",
                max_requests=2,
                window_seconds=60,
                block_seconds=30,
            ),
        ),
    )
    monkeypatch.setattr(rate_limit_middleware, "POLICIES", (policy,))

    app = _build_app()
    client = await async_client_factory(app)
    shared_ip_headers = {"X-Forwarded-For": "203.0.113.20"}
    user_one_headers = {
        **shared_ip_headers,
        "Authorization": f"Bearer {_token_for('user-1')}",
    }
    user_two_headers = {
        **shared_ip_headers,
        "Authorization": f"Bearer {_token_for('user-2')}",
    }

    assert (await client.post("/api/unified-chat/message", headers=user_one_headers)).status_code == 200
    assert (await client.post("/api/unified-chat/message", headers=user_one_headers)).status_code == 200

    blocked = await client.post("/api/unified-chat/message", headers=user_one_headers)
    assert blocked.status_code == 429
    assert blocked.json()["scope"] == "user"

    allowed_other_user = await client.post("/api/unified-chat/message", headers=user_two_headers)
    assert allowed_other_user.status_code == 200


@pytest.mark.asyncio
async def test_rate_limit_with_high_concurrency(monkeypatch: pytest.MonkeyPatch):
    policy = EndpointPolicy(
        name="test-chat-concurrency",
        prefixes=("/api/unified-chat/message",),
        methods=frozenset({"POST"}),
        rules=(
            RateLimitRule(
                name="test_chat_concurrency_ip",
                scope="ip",
                max_requests=500,
                window_seconds=60,
                block_seconds=30,
            ),
            RateLimitRule(
                name="test_chat_concurrency_user",
                scope="user",
                max_requests=40,
                window_seconds=60,
                block_seconds=30,
            ),
        ),
    )
    monkeypatch.setattr(rate_limit_middleware, "POLICIES", (policy,))

    app = _build_app()
    transport = httpx.ASGITransport(app=app)
    headers = {
        "X-Forwarded-For": "203.0.113.30",
        "Authorization": f"Bearer {_token_for('load-user')}",
    }

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        async def _request_once():
            response = await client.post("/api/unified-chat/message", headers=headers)
            return response.status_code

        results = await asyncio.gather(*[_request_once() for _ in range(120)])

    assert results.count(200) == 40
    assert results.count(429) == 80


@pytest.mark.asyncio
async def test_rate_limit_sustains_burst_load(monkeypatch: pytest.MonkeyPatch):
    policy = EndpointPolicy(
        name="test-chat-burst",
        prefixes=("/api/unified-chat/message",),
        methods=frozenset({"POST"}),
        rules=(
            RateLimitRule(
                name="test_chat_burst_ip",
                scope="ip",
                max_requests=5000,
                window_seconds=60,
                block_seconds=30,
            ),
            RateLimitRule(
                name="test_chat_burst_user",
                scope="user",
                max_requests=25,
                window_seconds=60,
                block_seconds=30,
            ),
        ),
    )
    monkeypatch.setattr(rate_limit_middleware, "POLICIES", (policy,))

    app = _build_app()
    transport = httpx.ASGITransport(app=app)
    users = [f"user-{index}" for index in range(10)]

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        async def _request_once(i: int):
            user_id = users[i % len(users)]
            headers = {
                "X-Forwarded-For": "203.0.113.40",
                "Authorization": f"Bearer {_token_for(user_id)}",
            }
            response = await client.post(
                "/api/unified-chat/message",
                headers=headers,
            )
            return response.status_code

        results = await asyncio.gather(*[_request_once(i) for i in range(1000)])

    assert results.count(200) == 250
    assert results.count(429) == 750
