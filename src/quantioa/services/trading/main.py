
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
import uvicorn
from aiokafka import AIOKafkaConsumer
import httpx

from quantioa.config import settings
from quantioa.engine.strategy import AITradingStrategy
from quantioa.models.enums import TradeSide
from quantioa.models.types import Tick, Position, Order
from quantioa.services.sentiment.cache import SentimentCache
from quantioa.portfolio.manager import PortfolioManager

logger = logging.getLogger(__name__)

# --- Global State ---
strategies: dict[str, AITradingStrategy] = {}
kafka_consumer: AIOKafkaConsumer | None = None
sentiment_cache: SentimentCache = SentimentCache()
portfolio_manager: PortfolioManager = PortfolioManager()

# Simulated state for position tracking
current_positions: dict[str, float] = {}
available_capital: float = 100_000.0

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

async def _execute_trade(symbol: str, side: str, capital_allocation: float):
    # Minimal stub to determine quantity. In production: fetch real price -> calculate qty
    # Assuming avg price ~1000 for mock testing purposes
    qty = max(int(capital_allocation / 1000.0), 1)
    
    order = Order(
        symbol=symbol,
        side=TradeSide.LONG if side == "BUY" else TradeSide.SHORT,
        quantity=qty
    )
    
    headers = {
        "broker_type": "UPSTOX",
        "user_id": "system_user"  # In multi-tenant, this comes from context
    }
    
    # We use the docker compose internal hostname: quantioa-broker
    # Note: If running locally outside docker, use localhost:8007
    url = "http://quantioa-broker:8000/orders"
    broker_host = os.environ.get("BROKER_SERVICE_URL", url)
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                broker_host,
                json=order.__dict__,
                headers=headers
            )
            resp.raise_for_status()
            logger.info("Successfully executed %s order via broker for %s", side, symbol)
    except Exception as e:
        logger.error("Failed to execute %s order for %s: %s", side, symbol, e)


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

                # Update rolling correlation price history
                if tick.close > 0:
                    portfolio_manager.update_price_history(symbol, tick.close)

                # Execute Strategy Logic
                decision = await strategy.on_tick(tick, indicators, position)
                
                signal = decision["signal"]
                if signal in ("BUY", "SELL"):
                    logger.info("TRADE DETECTED: %s %s", signal, symbol)
                    
                    if signal == "BUY":
                        allowed = portfolio_manager.is_trade_allowed(symbol, list(current_positions.keys()))
                        if allowed:
                            allocated = portfolio_manager.allocate_capital(
                                symbol=symbol, 
                                total_equity=available_capital, 
                                current_positions=current_positions
                            )
                            if allocated > 0:
                                logger.info("Portfolio Manager ALLOWED BUY %s: Allocated ₹%.2f", symbol, allocated)
                                current_positions[symbol] = current_positions.get(symbol, 0.0) + allocated
                                await _execute_trade(symbol, "BUY", allocated)
                            else:
                                logger.info("Portfolio Manager REJECTED BUY %s: Allocation limits reached", symbol)
                        else:
                            logger.info("Portfolio Manager REJECTED BUY %s: High correlation or limit breach", symbol)
                    
                    elif signal == "SELL":
                        if symbol in current_positions:
                            logger.info("Portfolio Manager CLOSING POSITION %s", symbol)
                            allocated_amount = current_positions[symbol]
                            del current_positions[symbol]
                            await _execute_trade(symbol, "SELL", allocated_amount)

                # Periodic Drift Check
                rebalance_actions = portfolio_manager.check_rebalance_needs(available_capital, current_positions)
                for action in rebalance_actions:
                    logger.info("REBALANCE REQUIRED for %s: Reduce exposure by ₹%.2f (%s)", 
                                action["symbol"], action["amount_to_reduce"], action["reason"])

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
