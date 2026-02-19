import pytest
import asyncio
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
def mock_kafka_consumer():
    # The import is already mocked, but we want to control the instance
    with patch("quantioa.services.trading.main.AIOKafkaConsumer") as mock_class:
        mock_consumer = AsyncMock()
        mock_class.return_value = mock_consumer
        yield mock_consumer

@pytest.fixture
def mock_strategy():
    strategy = AsyncMock()
    strategy.initialize = AsyncMock()
    strategy.on_tick = AsyncMock(return_value={
        "signal": "BUY",
        "confidence": 0.9,
        "reasoning": "Test reasoning",
        "sentiment_score": 0.5
    })
    return strategy

def test_health_check():
    """Verify health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "trading-engine"}

@pytest.mark.asyncio
async def test_process_ticks_with_strategy(mock_strategy):
    """Verify that process_ticks consumes messages and triggers the strategy."""
    
    # Inject mock strategy
    strategies["TEST_SYMBOL"] = mock_strategy
    
    # Create a mock message
    mock_msg = MagicMock()
    mock_msg.value = {
        "symbol": "TEST_SYMBOL",
        "timestamp": 1234567890,
        "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000
    }
    
    # Mock the Kafka consumer to yield one message then stop
    # We use an AsyncMock that acts as an async iterator
    mock_consumer = AsyncMock()
    mock_consumer.__aiter__.return_value = [mock_msg]
    
    # Patch the global kafka_consumer in main.py
    with patch("quantioa.services.trading.main.kafka_consumer", mock_consumer):
        await process_ticks()
    
    # Verify strategy was called
    mock_strategy.on_tick.assert_called_once()
    
    # Verify arguments passed to on_tick
    # tick, indicators, position
    args = mock_strategy.on_tick.call_args[0]
    tick = args[0]
    assert tick.symbol == "TEST_SYMBOL"
    assert tick.close == 105

@pytest.mark.asyncio
async def test_process_ticks_no_strategy():
    """Verify that ticks for unknown symbols are ignored."""
    strategies.clear()
    
    mock_msg = MagicMock()
    mock_msg.value = {"symbol": "UNKNOWN", "close": 100}
    
    mock_consumer = AsyncMock()
    mock_consumer.__aiter__.return_value = [mock_msg]
    
    with patch("quantioa.services.trading.main.kafka_consumer", mock_consumer):
        # Should run without error and do nothing
        await process_ticks()

