"""
Auth Service — Authentication, JWT tokens, OAuth2 integration.

Handles:
- User registration and login
- JWT access/refresh token management
- Upstox OAuth2 callback handling
- Role-based access control (RBAC)
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Quantioa Auth Service", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "auth-service"}


@app.post("/register")
async def register():
    """User registration stub."""
    return {"message": "Registration endpoint — to be implemented"}


@app.post("/login")
async def login():
    """User login stub."""
    return {"message": "Login endpoint — to be implemented"}


@app.get("/oauth/upstox/authorize")
async def upstox_authorize():
    """Redirect to Upstox OAuth2 authorization page."""
    from quantioa.broker.upstox_auth import UpstoxOAuth2

    auth = UpstoxOAuth2()
    return {"authorization_url": auth.get_authorization_url()}


@app.get("/oauth/upstox/callback")
async def upstox_callback(code: str):
    """Handle Upstox OAuth2 callback with authorization code."""
    return {"message": "OAuth callback — token exchange to be implemented", "code": code}
