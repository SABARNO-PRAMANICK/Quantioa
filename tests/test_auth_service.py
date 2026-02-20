"""
Tests for the Auth Service — registration, login, JWT, OAuth callbacks.
"""

from __future__ import annotations

import time

import bcrypt
import jwt
import pytest
from fastapi.testclient import TestClient

from quantioa.config import settings
from quantioa.services.auth.main import (
    _LOGIN_ATTEMPTS,
    _create_jwt,
    _decode_jwt,
    _issue_tokens,
    _users,
    app,
)

# Override JWT secret for tests
settings.jwt_secret_key = "test-secret-key-for-unit-tests"

client = TestClient(app)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clear_users():
    """Clear user store and rate limit state before each test."""
    _users.clear()
    _LOGIN_ATTEMPTS.clear()
    yield
    _users.clear()
    _LOGIN_ATTEMPTS.clear()


def _register_and_login(email: str = "test@example.com", password: str = "securepass123"):
    """Helper: register + login, return tokens."""
    client.post("/register", json={"email": email, "password": password})
    resp = client.post("/login", json={"email": email, "password": password})
    return resp.json()


# ── Health ────────────────────────────────────────────────────────────────────


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
    assert resp.json()["service"] == "auth-service"


# ── Registration ──────────────────────────────────────────────────────────────


def test_register_success():
    resp = client.post("/register", json={
        "email": "user@example.com",
        "password": "securepass123",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "user@example.com"
    assert data["role"] == "FREE_TRADER"
    assert "id" in data
    assert "created_at" in data


def test_register_duplicate_email():
    client.post("/register", json={"email": "dup@test.com", "password": "password123"})
    resp = client.post("/register", json={"email": "dup@test.com", "password": "password456"})
    assert resp.status_code == 409
    assert "already registered" in resp.json()["detail"]


def test_register_short_password():
    resp = client.post("/register", json={"email": "new@test.com", "password": "short"})
    assert resp.status_code == 400
    assert "8 characters" in resp.json()["detail"]


def test_register_invalid_email():
    resp = client.post("/register", json={"email": "not-an-email", "password": "password123"})
    assert resp.status_code == 422  # Pydantic validation


def test_register_password_is_hashed():
    client.post("/register", json={"email": "hash@test.com", "password": "securepass123"})
    user = _users["hash@test.com"]
    # Password should be bcrypt-hashed, not plaintext
    assert user["password_hash"] != "securepass123"
    assert bcrypt.checkpw(b"securepass123", user["password_hash"].encode("utf-8"))


# ── Login ─────────────────────────────────────────────────────────────────────


def test_login_success():
    client.post("/register", json={"email": "login@test.com", "password": "password123"})
    resp = client.post("/login", json={"email": "login@test.com", "password": "password123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] > 0


def test_login_wrong_password():
    client.post("/register", json={"email": "wrong@test.com", "password": "password123"})
    resp = client.post("/login", json={"email": "wrong@test.com", "password": "wrongpass"})
    assert resp.status_code == 401
    assert "Invalid email or password" in resp.json()["detail"]


def test_login_nonexistent_user():
    resp = client.post("/login", json={"email": "noone@test.com", "password": "password123"})
    assert resp.status_code == 401


# ── JWT Tokens ────────────────────────────────────────────────────────────────


def test_jwt_encode_decode():
    token = _create_jwt({"sub": "user-123", "type": "access"}, expires_in_seconds=3600)
    payload = _decode_jwt(token)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"
    assert "exp" in payload
    assert "iat" in payload
    assert "jti" in payload


def test_jwt_expired_token():
    token = _create_jwt({"sub": "user-123", "type": "access"}, expires_in_seconds=-1)
    with pytest.raises(Exception) as exc_info:
        _decode_jwt(token)
    assert exc_info.value.status_code == 401  # type: ignore


def test_jwt_invalid_token():
    with pytest.raises(Exception) as exc_info:
        _decode_jwt("not.a.valid.jwt")
    assert exc_info.value.status_code == 401  # type: ignore


def test_issue_tokens_returns_both():
    tokens = _issue_tokens("user-123", "test@test.com", "FREE_TRADER")
    assert tokens.access_token
    assert tokens.refresh_token
    assert tokens.expires_in > 0
    # Verify tokens are actually valid JWTs
    access_payload = jwt.decode(tokens.access_token, settings.jwt_secret_key, algorithms=["HS256"])
    assert access_payload["sub"] == "user-123"
    assert access_payload["type"] == "access"
    refresh_payload = jwt.decode(tokens.refresh_token, settings.jwt_secret_key, algorithms=["HS256"])
    assert refresh_payload["type"] == "refresh"


# ── Token Refresh ─────────────────────────────────────────────────────────────


def test_token_refresh():
    tokens = _register_and_login()
    resp = client.post("/token/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"] != tokens["access_token"]  # Should be new
    assert "refresh_token" in data


def test_token_refresh_with_access_token_fails():
    tokens = _register_and_login()
    resp = client.post("/token/refresh", json={"refresh_token": tokens["access_token"]})
    assert resp.status_code == 400
    assert "refresh token" in resp.json()["detail"]


# ── Protected Endpoints ──────────────────────────────────────────────────────


def test_me_endpoint():
    tokens = _register_and_login()
    resp = client.get("/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "test@example.com"
    assert data["role"] == "FREE_TRADER"


def test_me_without_token():
    resp = client.get("/me")
    assert resp.status_code == 422  # Missing header


def test_me_with_invalid_token():
    resp = client.get("/me", headers={"Authorization": "Bearer fake.jwt.token"})
    assert resp.status_code == 401


def test_me_with_non_bearer_auth():
    resp = client.get("/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert resp.status_code == 401
    assert "Bearer" in resp.json()["detail"]


# ── Upstox OAuth Authorize (requires JWT) ────────────────────────────────────


def test_upstox_authorize_requires_auth():
    resp = client.get("/oauth/upstox/authorize")
    assert resp.status_code == 422  # No auth header


def test_upstox_authorize_with_jwt():
    tokens = _register_and_login()
    resp = client.get(
        "/oauth/upstox/authorize",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "authorization_url" in data
    assert "upstox.com" in data["authorization_url"]


# ── Zerodha OAuth Authorize (requires JWT) ───────────────────────────────────


def test_zerodha_authorize_requires_auth():
    resp = client.get("/oauth/zerodha/authorize")
    assert resp.status_code == 422


def test_zerodha_authorize_with_jwt():
    tokens = _register_and_login()
    resp = client.get(
        "/oauth/zerodha/authorize",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "authorization_url" in data
    assert "zerodha" in data["authorization_url"]


# ── Broker Status (requires JWT) ─────────────────────────────────────────────


def test_broker_status_no_tokens():
    tokens = _register_and_login()
    resp = client.get(
        "/broker/status",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["upstox"]["connected"] is False
    assert data["zerodha"]["connected"] is False


# ── Rate Limiting ─────────────────────────────────────────────────────────────


def test_login_rate_limit_blocks_after_5_attempts():
    client.post("/register", json={"email": "rate@test.com", "password": "password123"})
    # Make 5 failed login attempts
    for _ in range(5):
        client.post("/login", json={"email": "rate@test.com", "password": "wrongpass"})
    # 6th attempt should be rate limited
    resp = client.post("/login", json={"email": "rate@test.com", "password": "password123"})
    assert resp.status_code == 429
    assert "15 minutes" in resp.json()["detail"]


def test_successful_login_clears_rate_limit():
    client.post("/register", json={"email": "clear@test.com", "password": "password123"})
    # 3 failed attempts
    for _ in range(3):
        client.post("/login", json={"email": "clear@test.com", "password": "wrongpass"})
    # Successful login should clear the counter
    resp = client.post("/login", json={"email": "clear@test.com", "password": "password123"})
    assert resp.status_code == 200
    # Now we should be able to fail again without hitting the limit
    resp = client.post("/login", json={"email": "clear@test.com", "password": "wrongpass"})
    assert resp.status_code == 401  # Not 429


# ── CORS ──────────────────────────────────────────────────────────────────────


def test_cors_headers_present():
    resp = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
