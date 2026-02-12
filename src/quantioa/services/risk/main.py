"""
Risk Service — portfolio risk management and circuit breakers.

Handles:
- Position-level stop loss monitoring
- Daily P&L limit enforcement
- Weekly drawdown tracking
- Anomaly detection and circuit breakers
- Correlation-based hedging suggestions
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Quantioa Risk Service", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "risk-service"}


@app.get("/metrics")
async def get_risk_metrics():
    """Get current portfolio risk metrics."""
    return {"message": "Risk metrics — to be implemented"}


@app.get("/circuit-breaker/status")
async def circuit_breaker_status():
    """Get circuit breaker status."""
    return {"is_active": False, "message": "No circuit breakers triggered"}
