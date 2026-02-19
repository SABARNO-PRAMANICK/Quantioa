
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
import uvicorn
from aiokafka import AIOKafkaConsumer

from quantioa.config import settings
from quantioa.engine.strategy import AITradingStrategy
from quantioa.models.types import Tick, Position
from quantioa.services.sentiment.cache import SentimentCache

logger = logging.getLogger(__name__)

# --- Global State ---
strategies: dict[str, AITradingStrategy] = {}
kafka_consumer: AIOKafkaConsumer | None = None
sentiment_cache: SentimentCache = SentimentCache()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and Shutdown logic."""
    global kafka_consumer
    
    # 1. Connect to Sentiment Cache
    await sentiment_cache.connect()
    
    # 2. Initialize Strategies (Example: NIFTY50)
    # in a real app, these might be started dynamically via API
    strategies["NIFTY50"] = AITradingStrategy("NIFTY50", cache=sentiment_cache)
    await strategies["NIFTY50"].initialize()
    
    # 3. Start Kafka Consumer
    loop = asyncio.get_event_loop()
    kafka_consumer = AIOKafkaConsumer(
        "market_data",
        bootstrap_servers=settings.kafka_bootstrap_servers.split(","),
        loop=loop,
        value_deserializer=lambda x: json.loads(x.decode('utf-8'))
    )
    await kafka_consumer.start()
    logger.info("Trading Engine started. Listening for ticks...")

    # Start the tick processing loop in background
    asyncio.create_task(process_ticks())

    yield

    # Shutdown
    if kafka_consumer:
        await kafka_consumer.stop()
    logger.info("Trading Engine stopped.")


app = FastAPI(title="Quantioa Trading Engine", version="0.1.0", lifespan=lifespan)

async def process_ticks():
    """Consume ticks from Kafka and feed them to strategies."""
    if not kafka_consumer:
        return

    try:
        async for msg in kafka_consumer:
            data = msg.value
            symbol = data.get("symbol")
            
            if symbol in strategies:
                strategy = strategies[symbol]
                
                # Convert raw dict to Tick object (simplified)
                tick = Tick(
                    timestamp=data.get("timestamp", 0),
                    symbol=symbol,
                    open=data.get("open", 0),
                    high=data.get("high", 0),
                    low=data.get("low", 0),
                    close=data.get("close", 0),
                    volume=data.get("volume", 0)
                )
                
                # Mock indicators/position for now
                # In production, these would be fetched from Data Service / Broker
                indicators = {
                    "rsi": 55.0, 
                    "macd_hist": 0.05,
                    "atr": 10.0
                }
                position = None # await broker.get_position(symbol)

                # Execute Strategy Logic
                decision = await strategy.on_tick(tick, indicators, position)
                
                if decision["signal"] in ("BUY", "SELL"):
                    logger.info("TRADE DETECTED: %s %s", decision["signal"], symbol)
                    # TODO: Execute trade via Broker Service

    except Exception as e:
        logger.error("Tick processing error: %s", e)

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "trading-engine"}

@app.get("/strategies")
async def list_strategies():
    return {"active": list(strategies.keys())}

if __name__ == "__main__":
    uvicorn.run("quantioa.services.trading.main:app", host="0.0.0.0", port=8002, reload=True)
