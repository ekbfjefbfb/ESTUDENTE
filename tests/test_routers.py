import httpx
import pytest
import pytest_asyncio

from main import app
from utils.auth import get_current_user


async def _override_current_user(credentials=None, db=None):
    return {"user_id": "u-1"}


@pytest_asyncio.fixture
async def client():
    await app.router.startup()
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as test_client:
            yield test_client
    finally:
        await app.router.shutdown()


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_root_endpoint_ok(client: httpx.AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "operational"
    assert body["health"] == "/api/health"


@pytest.mark.asyncio
async def test_api_health_endpoint_ok(client: httpx.AsyncClient):
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert "status" in body
    assert "components" in body


@pytest.mark.asyncio
async def test_unified_chat_health_ok(client: httpx.AsyncClient):
    response = await client.get("/api/unified-chat/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "unified-chat"


@pytest.mark.asyncio
async def test_unified_chat_info_limits_are_consistent(client: httpx.AsyncClient):
    response = await client.get("/api/unified-chat/info")
    assert response.status_code == 200
    body = response.json()
    assert body["limits"]["max_audio_size_mb"] == 10


@pytest.mark.asyncio
async def test_auth_login_invalid_email_returns_422(client: httpx.AsyncClient):
    response = await client.post(
        "/api/auth/login",
        json={"email": "no-email", "password": "12345678"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_not_found_contract(client: httpx.AsyncClient):
    response = await client.get("/api/route-that-does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "Not found"
    assert "/api/route-that-does-not-exist" in body["message"]


@pytest.mark.asyncio
async def test_cors_preflight_login_ok(client: httpx.AsyncClient):
    response = await client.options(
        "/api/auth/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_context_refresh_allows_same_user(client: httpx.AsyncClient):
    app.dependency_overrides[get_current_user] = _override_current_user
    response = await client.post("/api/unified-chat/context/refresh/u-1")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["user_id"] == "u-1"


@pytest.mark.asyncio
async def test_context_refresh_blocks_different_user(client: httpx.AsyncClient):
    app.dependency_overrides[get_current_user] = _override_current_user
    response = await client.post("/api/unified-chat/context/refresh/u-2")
    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden_user_id_mismatch"


@pytest.mark.asyncio
async def test_csrf_token_endpoint_ok(client: httpx.AsyncClient):
    response = await client.get("/api/csrf-token")
    assert response.status_code == 200
    body = response.json()
    assert "csrf_token" in body
    assert body["expires_in"] == 900
