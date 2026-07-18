import base64
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from httpx import Response

from src.api.auth import current_user
from src.api.connections import current_user as connection_current_user
from src.api.connection_repository import _encrypt
from src.api.main import app


client = TestClient(app)


def test_frontend_cors_allows_vite_loopback_and_exposes_auth_jwt() -> None:
    response = client.get("/", headers={"Origin": "http://127.0.0.1:5173"})

    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert response.headers["access-control-expose-headers"] == "set-auth-jwt"


def test_frontend_cors_allows_settings_patch() -> None:
    response = client.options(
        "/connections/connection-1/settings",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "PATCH",
        },
    )

    assert response.status_code == 200
    assert "PATCH" in response.headers["access-control-allow-methods"]


def test_signup_proxies_to_neon_auth(monkeypatch) -> None:
    monkeypatch.setenv("NEON_AUTH_BASE_URL", "https://auth.example.test/neondb/auth")
    request = AsyncMock(
        return_value=Response(
            201,
            json={"user": {"id": "user-1"}},
            headers={"set-auth-jwt": "token"},
        )
    )
    with patch("src.api.auth.httpx.AsyncClient.request", request):
        response = client.post(
            "/auth/signup",
            json={"name": "Ali", "email": "ali@example.com", "password": "Password-123"},
        )

    assert response.status_code == 201
    assert response.json() == {"user": {"id": "user-1"}}
    assert response.headers["set-auth-jwt"] == "token"
    assert request.await_args.args[1] == "https://auth.example.test/neondb/auth/sign-up/email"
    assert request.await_args.kwargs["headers"]["origin"] == "http://testserver"


def test_signup_requires_a_strong_password() -> None:
    response = client.post(
        "/auth/signup",
        json={"name": "Ali", "email": "ali@example.com", "password": "password"},
    )

    assert response.status_code == 422
    assert "uppercase" in response.json()["detail"][0]["msg"]


def test_login_accepts_existing_short_password(monkeypatch) -> None:
    monkeypatch.setenv("NEON_AUTH_BASE_URL", "https://auth.example.test/neondb/auth")
    request = AsyncMock(return_value=Response(200, json={"token": "jwt"}))
    with patch("src.api.auth.httpx.AsyncClient.request", request):
        response = client.post("/auth/login", json={"email": "ALI@EXAMPLE.COM ", "password": "legacy"})

    assert response.status_code == 200
    assert request.await_args.kwargs["json"]["email"] == "ali@example.com"


def test_new_connection_test_does_not_persist_credentials() -> None:
    app.dependency_overrides[connection_current_user] = lambda: {"sub": "user-1"}
    with patch("src.api.connections.psycopg2.connect") as connect:
        try:
            response = client.post("/connections/test", json={
                "display_name": "",
                "connection_url": "postgresql://readonly:p@ss@db.example.com:5432/app?sslmode=require",
            })
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    connect.assert_called_once_with(
        host="db.example.com", port=5432, database="app", user="readonly", password="p@ss",
        sslmode="require", connect_timeout=10,
    )


def test_token_proxy_does_not_send_json_content_type_without_a_body(monkeypatch) -> None:
    monkeypatch.setenv("NEON_AUTH_BASE_URL", "https://auth.example.test/neondb/auth")
    request = AsyncMock(return_value=Response(200, json={"token": "jwt"}))
    with patch("src.api.auth.httpx.AsyncClient.request", request):
        response = client.post("/auth/token")

    assert response.status_code == 200
    assert "content-type" not in request.await_args.kwargs["headers"]
    assert request.await_args.args[0] == "GET"
    assert request.await_args.args[1] == "https://auth.example.test/neondb/auth/get-session"


def test_logout_sends_an_empty_json_body(monkeypatch) -> None:
    monkeypatch.setenv("NEON_AUTH_BASE_URL", "https://auth.example.test/neondb/auth")
    request = AsyncMock(return_value=Response(200))
    with patch("src.api.auth.httpx.AsyncClient.request", request):
        response = client.post("/auth/logout")

    assert response.status_code == 204
    assert request.await_args.kwargs["json"] == {}
    assert request.await_args.kwargs["headers"]["content-type"] == "application/json"


def test_token_proxy_forwards_empty_non_json_response(monkeypatch) -> None:
    monkeypatch.setenv("NEON_AUTH_BASE_URL", "https://auth.example.test/neondb/auth")
    request = AsyncMock(return_value=Response(200, headers={"set-auth-jwt": "jwt"}))
    with patch("src.api.auth.httpx.AsyncClient.request", request):
        response = client.post("/auth/token")

    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["set-auth-jwt"] == "jwt"


def test_me_returns_verified_user() -> None:
    app.dependency_overrides[current_user] = lambda: {
        "sub": "user-1",
        "email": "ali@example.com",
        "role": "authenticated",
        "exp": 123,
    }
    try:
        response = client.get("/auth/me")
    finally:
        app.dependency_overrides.clear()

    assert response.json() == {
        "id": "user-1",
        "email": "ali@example.com",
        "role": "authenticated",
        "expires_at": 123,
    }


def test_connection_credentials_are_encrypted(monkeypatch) -> None:
    monkeypatch.setenv("APP_CREDENTIAL_MASTER_KEY", base64.urlsafe_b64encode(b"k" * 32).decode())
    encrypted = _encrypt("connection-1", {"password": "secret", "host": "db.example.com"})

    assert b"secret" not in encrypted["ciphertext"]
    assert encrypted["encrypted_data_key"]
    assert encrypted["auth_tag"]
