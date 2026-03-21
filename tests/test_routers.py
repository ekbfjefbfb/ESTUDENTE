import pytest
from fastapi.testclient import TestClient

from main import app
from utils.auth import get_current_user


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_root_endpoint_ok(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "operational"
    assert body["health"] == "/api/health"


def test_api_health_endpoint_ok(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert "status" in body
    assert "components" in body


def test_unified_chat_health_ok(client: TestClient):
    response = client.get("/api/unified-chat/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "unified-chat"


def test_unified_chat_info_limits_are_consistent(client: TestClient):
    response = client.get("/api/unified-chat/info")
    assert response.status_code == 200
    body = response.json()
    assert body["limits"]["max_audio_size_mb"] == 10


def test_auth_login_invalid_email_returns_422(client: TestClient):
    response = client.post(
        "/api/auth/login",
        json={"email": "no-email", "password": "12345678"},
    )
    assert response.status_code == 422


def test_not_found_contract(client: TestClient):
    response = client.get("/api/route-that-does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "Not found"
    assert "/api/route-that-does-not-exist" in body["message"]


def test_cors_preflight_login_ok(client: TestClient):
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200


def test_context_refresh_allows_same_user(client: TestClient):
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u-1"}
    response = client.post("/api/unified-chat/context/refresh/u-1")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["user_id"] == "u-1"


def test_context_refresh_blocks_different_user(client: TestClient):
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u-1"}
    response = client.post("/api/unified-chat/context/refresh/u-2")
    assert response.status_code == 403
    assert response.json()["detail"] == "forbidden_user_id_mismatch"


def test_csrf_token_endpoint_ok(client: TestClient):
    response = client.get("/api/csrf-token")
    assert response.status_code == 200
    body = response.json()
    assert "csrf_token" in body
    assert body["expires_in"] == 900
