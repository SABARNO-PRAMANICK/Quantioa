"""
Data Service — market data collection and streaming.

Handles:
- OHLCV historical data collection
- WebSocket market data streaming from Upstox
- Candle aggregation (1M → 5M → 15M → 1H → 4H → 1D)
- Data storage to TimescaleDB / PostgreSQL
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Quantioa Data Service", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "data-service"}


@app.get("/ohlcv/{symbol}")
async def get_ohlcv(symbol: str, interval: str = "1D", limit: int = 100):
    """Get historical OHLCV data."""
    return {"symbol": symbol, "interval": interval, "limit": limit, "data": []}


@app.get("/stream/{symbol}")
async def stream_info(symbol: str):
    """Get streaming connection info for a symbol."""
    return {"symbol": symbol, "message": "WebSocket streaming — to be implemented"}
