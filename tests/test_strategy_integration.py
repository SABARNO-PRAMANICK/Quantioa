
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from quantioa.engine.strategy import AITradingStrategy
from quantioa.models.types import Tick, Position, TradeSignal

@pytest.fixture
def mock_sentiment_cache():
    cache = MagicMock()
    cache.connect = AsyncMock()
    # Mock cache.get to return a dict as expected by SentimentReader
    cache.get = AsyncMock(return_value={
        "score": 0.8,
        "summary": "Bullish sentiment detected.",
        "confidence": 0.9,
        "_cached_at": 1234567890
    })
    return cache

@pytest.mark.asyncio
async def test_ai_strategy_workflow(mock_sentiment_cache):
    """
    Verify that AITradingStrategy correctly:
    1. Initializes
    2. Fetches sentiment (via reader/cache)
    3. Invokes LangGraph
    4. Returns a decision structure
    """
    
    # Mock the graph invocation to avoid real LLM calls
    mock_workflow_result = {
        "final_signal": "BUY",
        "confidence": 0.85,
        "reasoning": "Technical indicators align with bullish sentiment.",
        "sentiment_score": 0.8
    }
    
    with patch("quantioa.engine.strategy.build_trading_decision_graph") as mock_build_graph:
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = mock_workflow_result
        mock_build_graph.return_value = mock_graph
        
        strategy = AITradingStrategy("NIFTY50", cache=mock_sentiment_cache)
        await strategy.initialize()
        
        # Verify cache connection
        mock_sentiment_cache.connect.assert_called_once()
        
        # Simulate a tick
        tick = Tick(timestamp=1000, symbol="NIFTY50", open=100, high=105, low=99, close=104, volume=1000)
        indicators = {"rsi": 65.0, "macd_hist": 0.1}
        
        decision = await strategy.on_tick(tick, indicators, None)
        
        # Verify output structure
        assert decision["signal"] == "BUY"
        assert decision["confidence"] == 0.85
        assert decision["sentiment_score"] == 0.8
        
        # Verify graph was called with correct state
        mock_graph.ainvoke.assert_called_once()
        call_args = mock_graph.ainvoke.call_args[0][0]
        assert call_args["symbol"] == "NIFTY50"
        assert call_args["indicators"] == indicators
