"""
Data Service — market data collection and streaming.

Handles:
- OHLCV historical data collection
- WebSocket market data streaming from Upstox
- Candle aggregation (1M → 5M → 15M → 1H → 4H → 1D)
- Data storage to TimescaleDB / PostgreSQL
"""

from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio
import os
import time
import logging

from quantioa.services.data.upstox_ws import UpstoxWebSocketClient
from quantioa.services.data.kafka_producer import MarketDataPublisher
from quantioa.services.data.fast_path import FastPathRiskGuard
from quantioa.portfolio.universe import NIFTY_50_STOCKS

logger = logging.getLogger(__name__)

# --- Global State ---
market_publisher: MarketDataPublisher | None = None
ws_client: UpstoxWebSocketClient | None = None
fast_path_guard: FastPathRiskGuard | None = None

async def process_incoming_tick(tick):
    """Callback for every tick received from the broker WS."""
    t0_ns = time.time_ns()
    
    # 1. Evaluate Fast-Path Risk Guard (Sub-10ms bypass)
    if fast_path_guard:
        await fast_path_guard.evaluate_tick(tick)
        
    # 2. Publish to Kafka (Fire & Forget)
    if market_publisher:
        # Include T0 for latency tracing in downstream Engine
        import dataclasses
        tick_dict = dataclasses.asdict(tick)
        tick_dict["_t0_kafka_in_ns"] = t0_ns
        await market_publisher.publish_tick(tick_dict)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global market_publisher, ws_client, fast_path_guard
    
    # 1. Start Kafka Publisher
    market_publisher = MarketDataPublisher(topic="market_data")
    await market_publisher.connect()
    
    # 2. Start Fast-Path Guard
    fast_path_guard = FastPathRiskGuard()

    # 3. Start WebSocket Client
    api_key = os.environ.get("UPSTOX_API_KEY", "")
    access_token = os.environ.get("UPSTOX_ACCESS_TOKEN", "")
    
    if not api_key or not access_token:
        logger.warning("Upstox credentials missing. WebSocket may fail to authenticate.")
    
    ws_client = UpstoxWebSocketClient(api_key=api_key, access_token=access_token)
    ws_client.register_callback(process_incoming_tick)
    
    # Determine instruments to subscribe to (e.g., NIFTY 50 universe)
    # in reality, instruments need to be resolved to exchange tokens
    ws_client.subscribe(list(NIFTY_50_STOCKS.keys())[:10]) # Mocking first 10
    
    asyncio.create_task(ws_client.connect_and_listen())
    
    yield
    
    if market_publisher:
        await market_publisher.close()
    if fast_path_guard:
        await fast_path_guard.client.aclose()


app = FastAPI(title="Quantioa Data Service", version="0.1.0", lifespan=lifespan)


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
