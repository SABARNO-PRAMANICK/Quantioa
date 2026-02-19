"""
Integration tests for AITradingStrategy.

Tests: full workflow, error handling fallback, HOLD on low confidence.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from quantioa.engine.strategy import AITradingStrategy
from quantioa.models.types import Tick


@pytest.fixture
def mock_sentiment_cache():
    cache = MagicMock()
    cache.connect = AsyncMock()
    cache.get = AsyncMock(return_value={
        "score": 0.8,
        "summary": "Bullish sentiment detected.",
        "confidence": 0.9,
        "_cached_at": 1234567890,
    })
    return cache


def _make_tick(symbol="NIFTY50", close=104):
    return Tick(
        timestamp=1000, symbol=symbol,
        open=100, high=105, low=99, close=close, volume=1000,
    )


# ── Happy Path ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ai_strategy_workflow(mock_sentiment_cache):
    """Full pipeline: init → tick → decision with expected structure."""
    mock_result = {
        "final_signal": "BUY",
        "confidence": 0.85,
        "reasoning": "Technical indicators align with bullish sentiment.",
        "sentiment_score": 0.8,
    }

    with patch("quantioa.engine.strategy.build_trading_decision_graph") as mock_build:
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = mock_result
        mock_build.return_value = mock_graph

        strategy = AITradingStrategy("NIFTY50", cache=mock_sentiment_cache)
        await strategy.initialize()

        mock_sentiment_cache.connect.assert_called_once()

        decision = await strategy.on_tick(
            _make_tick(), {"rsi": 65.0, "macd_hist": 0.1}, None
        )

        assert decision["signal"] == "BUY"
        assert decision["confidence"] == 0.85
        assert decision["sentiment_score"] == 0.8

        call_state = mock_graph.ainvoke.call_args[0][0]
        assert call_state["symbol"] == "NIFTY50"
        assert call_state["indicators"]["rsi"] == 65.0


# ── Error Handling ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_strategy_error_returns_hold(mock_sentiment_cache):
    """Graph exception should be caught and returned as HOLD."""
    with patch("quantioa.engine.strategy.build_trading_decision_graph") as mock_build:
        mock_graph = AsyncMock()
        mock_graph.ainvoke.side_effect = RuntimeError("LLM timeout")
        mock_build.return_value = mock_graph

        strategy = AITradingStrategy("NIFTY50", cache=mock_sentiment_cache)
        await strategy.initialize()

        decision = await strategy.on_tick(_make_tick(), {"rsi": 50.0}, None)

        assert decision["signal"] == "HOLD"
        assert decision["confidence"] == 0.0
        assert "Strategy Error" in decision["reasoning"]


# ── HOLD Signal ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_strategy_hold_signal(mock_sentiment_cache):
    """Graph returning HOLD with low confidence."""
    mock_result = {
        "final_signal": "HOLD",
        "confidence": 0.2,
        "reasoning": "Mixed signals.",
        "sentiment_score": 0.0,
    }

    with patch("quantioa.engine.strategy.build_trading_decision_graph") as mock_build:
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = mock_result
        mock_build.return_value = mock_graph

        strategy = AITradingStrategy("NIFTY50", cache=mock_sentiment_cache)
        await strategy.initialize()

        decision = await strategy.on_tick(_make_tick(), {"rsi": 50.0}, None)

        assert decision["signal"] == "HOLD"
        assert decision["confidence"] == 0.2


# ── With Position Context ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_strategy_with_position(mock_sentiment_cache):
    """Strategy should include position data in state when provided."""
    from quantioa.models.types import Position
    from quantioa.models.enums import TradeSide

    position = Position(
        id="P1", symbol="NIFTY50", side=TradeSide.LONG,
        quantity=1, entry_price=22000.0, current_price=22100.0,
    )

    mock_result = {
        "final_signal": "SELL",
        "confidence": 0.7,
        "reasoning": "Exit position.",
        "sentiment_score": -0.3,
    }

    with patch("quantioa.engine.strategy.build_trading_decision_graph") as mock_build:
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = mock_result
        mock_build.return_value = mock_graph

        strategy = AITradingStrategy("NIFTY50", cache=mock_sentiment_cache)
        await strategy.initialize()

        decision = await strategy.on_tick(
            _make_tick(), {"rsi": 72.0}, position
        )

        assert decision["signal"] == "SELL"
        assert decision["confidence"] == 0.7
