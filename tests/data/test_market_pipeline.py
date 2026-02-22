"""
Tests for Data pipeline and Fast-Path bypass.
"""

import pytest
import time
import json
from unittest.mock import AsyncMock, patch
import httpx

from quantioa.models.types import Tick
from quantioa.services.data.fast_path import FastPathRiskGuard
from quantioa.services.data.kafka_producer import MarketDataPublisher


@pytest.fixture
def mock_tick():
    return Tick(
        timestamp=time.time(),
        symbol="NIFTY50",
        open=22000.0,
        high=22050.0,
        low=21950.0,
        close=22010.0,
        volume=1000
    )

@pytest.mark.asyncio
async def test_fast_path_stop_loss_long_triggered(mock_tick):
    """Test the sub-10ms bypass when a long position stop loss is breached."""
    
    with patch("quantioa.services.data.fast_path.httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value = mock_instance
        
        async with FastPathRiskGuard() as guard:
            # Register a stop loss ABOVE current price to trigger immediately
            guard.register_position("NIFTY50", "LONG", stop_loss=22020.0, quantity=50)
            
            # Close is 22010.0 <= 22020.0 (Triggered!)
            triggered = await guard.evaluate_tick(mock_tick)
            
            assert triggered is True
            # Verify the position was removed from watch
            assert "NIFTY50" not in guard._active_guards
            
            # Wait a tiny bit for the async fire-and-forget task to launch
            import asyncio
            await asyncio.sleep(0.01)
            
            # Check if HTTTP POST was fired to the broker with Market SELL
            mock_instance.post.assert_called_once()
            call_kwargs = mock_instance.post.call_args[1]
            assert call_kwargs["json"]["side"] == "SELL"
            assert call_kwargs["json"]["order_type"] == "MARKET"
            assert call_kwargs["json"]["quantity"] == 50

@pytest.mark.asyncio
async def test_fast_path_not_triggered_if_safe(mock_tick):
    """Test bypass does not trigger if price is safe."""
    async with FastPathRiskGuard() as guard:
        # Register a stop loss safely BELOW current price
        guard.register_position("NIFTY50", "LONG", stop_loss=21900.0, quantity=50)
        
        # Close is 22010.0 > 21900.0 (Safe)
        triggered = await guard.evaluate_tick(mock_tick)
        assert triggered is False
        assert "NIFTY50" in guard._active_guards

@pytest.mark.asyncio
async def test_latency_budget_serialization(mock_tick):
    """Benchmark test measuring Python to JSON serialization latency."""
    
    t0_ns = time.time_ns()
    
    import dataclasses
    tick_dict = dataclasses.asdict(mock_tick)
    tick_dict["_t0_kafka_in_ns"] = t0_ns
    encoded = json.dumps(tick_dict).encode("utf-8")
    
    t1_ns = time.time_ns()
    
    latency_ms = (t1_ns - t0_ns) / 1_000_000.0
    
    # Must serialize in sub-1ms (typically ~0.02ms)
    assert latency_ms < 1.0

@pytest.mark.asyncio
async def test_kafka_producer_formatting(mock_tick):
    """Ensure producer formats tick dictionary correctly."""
    
    with patch("quantioa.services.data.kafka_producer.AIOKafkaProducer") as mock_producer_cls:
        mock_producer = AsyncMock()
        mock_producer_cls.return_value = mock_producer
        
        async with MarketDataPublisher(topic="test_market_data") as pub:
            import dataclasses
            await pub.publish_tick(dataclasses.asdict(mock_tick))
            
            mock_producer.send.assert_called_once()
            args, kwargs = mock_producer.send.call_args
            assert args[0] == "test_market_data"
            assert kwargs["value"]["symbol"] == "NIFTY50"
