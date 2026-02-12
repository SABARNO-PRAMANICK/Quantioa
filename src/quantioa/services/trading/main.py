"""
Trading Engine Service — signal generation and trade execution.

Handles:
- Running the 30s trading loop
- Combining all 8 increments into final signals
- Trade confirmation gate
- Order execution via broker service
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Quantioa Trading Engine", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "trading-engine"}


@app.get("/signals/{symbol}")
async def get_signal(symbol: str):
    """Get the current signal for a symbol."""
    return {"symbol": symbol, "message": "Signal generation — to be implemented"}


@app.post("/strategies/{strategy_id}/start")
async def start_strategy(strategy_id: str):
    """Start a trading strategy."""
    return {"strategy_id": strategy_id, "status": "starting"}


@app.post("/strategies/{strategy_id}/stop")
async def stop_strategy(strategy_id: str):
    """Stop a trading strategy."""
    return {"strategy_id": strategy_id, "status": "stopped"}
