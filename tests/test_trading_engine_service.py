"""
Unit tests for the trading engine FastAPI service.

Tests: health check, process_ticks with strategy, unknown symbol handling.
"""

import pytest
import sys
from unittest.mock import MagicMock, AsyncMock, patch

# MOCK aiokafka BEFORE importing main
mock_aiokafka = MagicMock()
mock_aiokafka.AIOKafkaConsumer = MagicMock()
sys.modules["aiokafka"] = mock_aiokafka

from fastapi.testclient import TestClient
from quantioa.services.trading.main import app, process_ticks, strategies

client = TestClient(app)


@pytest.fixture
def mock_strategy():
    strategy = AsyncMock()
    strategy.initialize = AsyncMock()
    strategy.on_tick = AsyncMock(return_value={
        "signal": "BUY",
        "confidence": 0.9,
        "reasoning": "Test reasoning",
        "sentiment_score": 0.5,
    })
    return strategy


@pytest.fixture(autouse=True)
def _clean_strategies():
    """Ensure strategies dict is clean before each test."""
    strategies.clear()
    yield
    strategies.clear()


# ── Health Check ─────────────────────────────────────────────────────────


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "trading-engine"}


# ── Tick Processing ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_ticks_with_strategy(mock_strategy):
    """process_ticks should consume one Kafka message and call the strategy."""
    strategies["TEST_SYMBOL"] = mock_strategy

    mock_msg = MagicMock()
    mock_msg.value = {
        "symbol": "TEST_SYMBOL",
        "timestamp": 1234567890,
        "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000,
    }

    # Build a proper async iterator
    async def _aiter():
        yield mock_msg

    mock_consumer = MagicMock()
    mock_consumer.__aiter__ = lambda self: _aiter()

    with patch("quantioa.services.trading.main.kafka_consumer", mock_consumer):
        await process_ticks()

    mock_strategy.on_tick.assert_called_once()
    tick = mock_strategy.on_tick.call_args[0][0]
    assert tick.symbol == "TEST_SYMBOL"
    assert tick.close == 105


@pytest.mark.asyncio
async def test_process_ticks_no_strategy():
    """Ticks for unknown symbols should be silently ignored."""
    mock_msg = MagicMock()
    mock_msg.value = {"symbol": "UNKNOWN", "close": 100}

    async def _aiter():
        yield mock_msg

    mock_consumer = MagicMock()
    mock_consumer.__aiter__ = lambda self: _aiter()

    with patch("quantioa.services.trading.main.kafka_consumer", mock_consumer):
        await process_ticks()

    # No error — just ignored


@pytest.mark.asyncio
async def test_process_ticks_multiple_messages(mock_strategy):
    """Multiple messages should each be processed."""
    strategies["SYM"] = mock_strategy

    messages = []
    for i in range(3):
        msg = MagicMock()
        msg.value = {
            "symbol": "SYM", "timestamp": i,
            "open": 100, "high": 110, "low": 90, "close": 100 + i, "volume": 1000,
        }
        messages.append(msg)

    async def _aiter():
        for m in messages:
            yield m

    mock_consumer = MagicMock()
    mock_consumer.__aiter__ = lambda self: _aiter()

    with patch("quantioa.services.trading.main.kafka_consumer", mock_consumer):
        await process_ticks()

    assert mock_strategy.on_tick.call_count == 3
