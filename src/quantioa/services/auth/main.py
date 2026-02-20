"""
Auth Service — Authentication, JWT tokens, OAuth2 broker integration.

Handles:
- User registration and login (bcrypt password hashing)
- JWT access/refresh token management
- Upstox OAuth2 callback (code → token → store)
- Zerodha OAuth2 callback (request_token → access_token → store)
- Token refresh and validation
- JWT-protected dependency injection
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import bcrypt
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

from quantioa.broker.token_store import TokenStore
from quantioa.config import settings

logger = logging.getLogger(__name__)

app = FastAPI(title="Quantioa Auth Service", version="0.1.0")

# ── CORS ──────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # Dev frontends
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup Validation ────────────────────────────────────────────────────────


@app.on_event("startup")
async def _validate_config():
    """Ensure critical config is set before accepting requests."""
    if not settings.jwt_secret_key or settings.jwt_secret_key == "":
        raise RuntimeError(
            "JWT_SECRET_KEY is not set. Set it in .env or environment variables."
        )
    if len(settings.jwt_secret_key) < 32:
        logger.warning(
            "JWT_SECRET_KEY is %d bytes — recommend >= 32 bytes for HS256",
            len(settings.jwt_secret_key),
        )
    logger.info("Auth service started, JWT configured (algo=%s)", settings.jwt_algorithm)


# ── Rate Limiting (login brute-force protection) ──────────────────────────────

_LOGIN_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_MAX_LOGIN_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 900  # 15 minutes


def _check_rate_limit(email: str) -> None:
    """Block login if too many failed attempts in the window."""
    now = time.time()
    # Prune old entries
    _LOGIN_ATTEMPTS[email] = [
        t for t in _LOGIN_ATTEMPTS[email]
        if now - t < _LOGIN_WINDOW_SECONDS
    ]
    if len(_LOGIN_ATTEMPTS[email]) >= _MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again in 15 minutes.",
        )


def _record_failed_attempt(email: str) -> None:
    _LOGIN_ATTEMPTS[email].append(time.time())


def _clear_attempts(email: str) -> None:
    _LOGIN_ATTEMPTS.pop(email, None)

# ── In-memory user store (Phase 2 migrates to PostgreSQL) ─────────────────────
# Format: {email: {id, email, password_hash, role, created_at}}
_users: dict[str, dict[str, Any]] = {}
_token_store: TokenStore | None = None


def _get_token_store() -> TokenStore:
    """Lazily initialize the TokenStore (avoids startup Redis errors in tests)."""
    global _token_store
    if _token_store is None:
        _token_store = TokenStore()
    return _token_store


# ── Request/Response Models ───────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str  # min 8 chars enforced below


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    created_at: str


# ── JWT Helpers ───────────────────────────────────────────────────────────────


def _create_jwt(
    payload: dict[str, Any],
    expires_in_seconds: int,
) -> str:
    """Create a signed JWT with expiration."""
    now = time.time()
    claims = {
        **payload,
        "iat": int(now),
        "exp": int(now + expires_in_seconds),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _decode_jwt(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises HTTPException on failure."""
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        )


def _issue_tokens(user_id: str, email: str, role: str) -> TokenResponse:
    """Issue JWT access + refresh tokens for a user."""
    access_expires = settings.jwt_access_token_expire_minutes * 60
    refresh_expires = settings.jwt_refresh_token_expire_days * 86400

    access_token = _create_jwt(
        {"sub": user_id, "email": email, "role": role, "type": "access"},
        access_expires,
    )
    refresh_token = _create_jwt(
        {"sub": user_id, "email": email, "role": role, "type": "refresh"},
        refresh_expires,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=access_expires,
    )


# ── JWT Auth Dependency ──────────────────────────────────────────────────────


async def get_current_user(
    authorization: str = Header(..., description="Bearer <JWT>"),
) -> dict[str, Any]:
    """FastAPI dependency — extract and validate JWT from Authorization header.

    Usage in other services::

        @app.get("/protected")
        async def protected(user = Depends(get_current_user)):
            return {"user_id": user["sub"]}
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must start with 'Bearer'",
        )

    token = authorization[7:]
    payload = _decode_jwt(token)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expected an access token, got refresh token",
        )

    return payload


# ── Health ────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "auth-service"}


# ── Registration ──────────────────────────────────────────────────────────────


@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest):
    """Register a new user with email + password.

    Passwords are hashed with bcrypt before storage.
    """
    if len(req.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )

    if req.email in _users:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user_id = str(uuid.uuid4())
    password_hash = bcrypt.hashpw(
        req.password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")

    now = datetime.now(timezone.utc).isoformat()

    user = {
        "id": user_id,
        "email": req.email,
        "password_hash": password_hash,
        "role": "FREE_TRADER",
        "created_at": now,
    }
    _users[req.email] = user

    logger.info("User registered: %s (id=%s)", req.email, user_id)

    return UserResponse(
        id=user_id,
        email=req.email,
        role="FREE_TRADER",
        created_at=now,
    )


# ── Login ─────────────────────────────────────────────────────────────────────


@app.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """Authenticate with email + password, receive JWT tokens.

    Rate-limited: max 5 attempts per email per 15-minute window.
    """
    _check_rate_limit(req.email)

    user = _users.get(req.email)
    if user is None:
        _record_failed_attempt(req.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not bcrypt.checkpw(
        req.password.encode("utf-8"),
        user["password_hash"].encode("utf-8"),
    ):
        _record_failed_attempt(req.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    _clear_attempts(req.email)
    logger.info("User logged in: %s", req.email)

    return _issue_tokens(user["id"], user["email"], user["role"])


# ── Token Refresh ─────────────────────────────────────────────────────────────


@app.post("/token/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest):
    """Issue new access + refresh tokens using a valid refresh token."""
    payload = _decode_jwt(req.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Expected a refresh token",
        )

    return _issue_tokens(payload["sub"], payload["email"], payload["role"])


# ── Token Introspection ──────────────────────────────────────────────────────


@app.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Get current user info from JWT."""
    return {
        "user_id": user["sub"],
        "email": user["email"],
        "role": user["role"],
    }


# ── Upstox OAuth2 ────────────────────────────────────────────────────────────


@app.get("/oauth/upstox/authorize")
async def upstox_authorize(
    user: dict = Depends(get_current_user),
):
    """Generate Upstox OAuth2 authorization URL.

    The user must be logged in (JWT required) so we can associate
    the broker tokens with their account.
    """
    from quantioa.broker.upstox_auth import UpstoxOAuth2

    auth = UpstoxOAuth2()
    # Use user_id as state for CSRF protection + user association
    url = auth.get_authorization_url(state=user["sub"])

    return {"authorization_url": url, "state": user["sub"]}


@app.get("/oauth/upstox/callback")
async def upstox_callback(
    code: str = Query(..., description="Authorization code from Upstox"),
    state: str = Query("", description="User ID passed as state parameter"),
):
    """Handle Upstox OAuth2 callback.

    Exchanges the authorization code for tokens and persists them
    via TokenStore (Redis + file backup).
    """
    from quantioa.broker.upstox_auth import UpstoxOAuth2, UpstoxAuthError

    auth = UpstoxOAuth2()
    try:
        token_pair = await auth.exchange_code(code)

        # Use the state (user_id) or fall back to the Upstox user_id
        user_id = state or token_pair.user_id or "default"

        store = _get_token_store()
        store.save(user_id, "UPSTOX", token_pair)

        logger.info(
            "Upstox OAuth complete: user=%s, upstox_user=%s, exchanges=%s",
            user_id,
            token_pair.user_id,
            token_pair.exchanges,
        )

        return {
            "status": "success",
            "broker": "UPSTOX",
            "user_id": user_id,
            "upstox_user_id": token_pair.user_id,
            "exchanges": token_pair.exchanges,
            "token_stored": True,
        }

    except UpstoxAuthError as e:
        logger.error("Upstox OAuth failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Upstox authentication failed: {e}",
        )
    finally:
        await auth.close()


# ── Zerodha OAuth2 ───────────────────────────────────────────────────────────


@app.get("/oauth/zerodha/authorize")
async def zerodha_authorize(
    user: dict = Depends(get_current_user),
):
    """Generate Zerodha login URL."""
    from quantioa.broker.zerodha_auth import ZerodhaOAuth2

    auth = ZerodhaOAuth2()
    url = auth.get_authorization_url()

    return {"authorization_url": url, "user_id": user["sub"]}


@app.get("/oauth/zerodha/callback")
async def zerodha_callback(
    request_token: str = Query(..., description="Request token from Zerodha callback"),
    state: str = Query("", description="User ID"),
):
    """Handle Zerodha OAuth2 callback.

    Exchanges the request_token for an access_token using
    SHA-256 checksum authentication.
    """
    from quantioa.broker.zerodha_auth import ZerodhaAuthError, ZerodhaOAuth2

    auth = ZerodhaOAuth2()
    try:
        token_pair = await auth.exchange_token(request_token)

        user_id = state or token_pair.user_id or "default"

        store = _get_token_store()
        store.save(user_id, "ZERODHA", token_pair)

        logger.info(
            "Zerodha OAuth complete: user=%s, zerodha_user=%s",
            user_id,
            token_pair.user_id,
        )

        return {
            "status": "success",
            "broker": "ZERODHA",
            "user_id": user_id,
            "zerodha_user_id": token_pair.user_id,
            "exchanges": token_pair.exchanges,
            "token_stored": True,
        }

    except ZerodhaAuthError as e:
        logger.error("Zerodha OAuth failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Zerodha authentication failed: {e}",
        )
    finally:
        await auth.close()


# ── Broker Token Status ──────────────────────────────────────────────────────


@app.get("/broker/status")
async def broker_token_status(user: dict = Depends(get_current_user)):
    """Check which broker tokens are stored for the current user."""
    store = _get_token_store()
    user_id = user["sub"]

    upstox_token = store.load(user_id, "UPSTOX")
    zerodha_token = store.load(user_id, "ZERODHA")

    return {
        "user_id": user_id,
        "upstox": {
            "connected": upstox_token is not None,
            "expired": upstox_token.is_expired if upstox_token else None,
            "user_id": upstox_token.user_id if upstox_token else None,
        },
        "zerodha": {
            "connected": zerodha_token is not None,
            "expired": zerodha_token.is_expired if zerodha_token else None,
            "user_id": zerodha_token.user_id if zerodha_token else None,
        },
    }

