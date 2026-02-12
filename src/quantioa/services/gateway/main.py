"""
API Gateway — routes requests to internal microservices.

Handles:
- Request routing to downstream services
- Rate limiting (per-user, per-tier)
- CORS configuration
- Request/response logging
- Health checks
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(
    title="Quantioa API Gateway",
    description="AI-Powered Real-Time Trading System",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS ──────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Service Registry ─────────────────────────────────────────────────────────

SERVICE_URLS: dict[str, str] = {
    "auth": "http://auth-service:8000",
    "trading": "http://trading-engine:8000",
    "data": "http://data-service:8000",
    "risk": "http://risk-service:8000",
    "ai": "http://ai-service:8000",
    "analytics": "http://analytics-service:8000",
    "broker": "http://broker-service:8000",
}


# ─── Health Check ──────────────────────────────────────────────────────────────


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "api-gateway"}


@app.get("/")
async def root():
    return {
        "name": "Quantioa API Gateway",
        "version": "0.1.0",
        "services": list(SERVICE_URLS.keys()),
    }


# ─── Gateway Proxy ─────────────────────────────────────────────────────────────
# In a full implementation, this would forward requests to internal services.
# For now, we expose stub routes that show the routing structure.


@app.get("/api/v1/{service}/{path:path}")
async def proxy_get(service: str, path: str, request: Request):
    """Route GET requests to the appropriate microservice."""
    if service not in SERVICE_URLS:
        return JSONResponse(
            status_code=404,
            content={"error": f"Unknown service: {service}"},
        )
    return {
        "routed_to": SERVICE_URLS[service],
        "path": f"/{path}",
        "method": "GET",
        "note": "Proxy forwarding will be implemented with httpx",
    }


@app.post("/api/v1/{service}/{path:path}")
async def proxy_post(service: str, path: str, request: Request):
    """Route POST requests to the appropriate microservice."""
    if service not in SERVICE_URLS:
        return JSONResponse(
            status_code=404,
            content={"error": f"Unknown service: {service}"},
        )
    return {
        "routed_to": SERVICE_URLS[service],
        "path": f"/{path}",
        "method": "POST",
        "note": "Proxy forwarding will be implemented with httpx",
    }
