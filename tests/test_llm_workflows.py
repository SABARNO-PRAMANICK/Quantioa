"""
Unit tests for the LangGraph workflow components.

Tests: _extract_json, should_retry, generate_signal, full graph (mocked LLM).
"""

import pytest
from unittest.mock import AsyncMock, patch

from quantioa.llm.workflows import (
    _extract_json,
    should_retry,
    generate_signal,
    build_trading_decision_graph,
)


# ── _extract_json ────────────────────────────────────────────────────────


class TestExtractJson:
    def test_direct_json(self):
        result = _extract_json('{"key": "value", "num": 42}')
        assert result == {"key": "value", "num": 42}

    def test_markdown_json_fence(self):
        text = 'Some text\n```json\n{"answer": true}\n```\nmore text'
        assert _extract_json(text) == {"answer": True}

    def test_markdown_plain_fence(self):
        text = 'Explanation:\n```\n{"x": 1}\n```'
        assert _extract_json(text) == {"x": 1}

    def test_embedded_json_object(self):
        text = 'The result is {"score": 0.5, "signal": "BUY"} as expected.'
        result = _extract_json(text)
        assert result["score"] == 0.5
        assert result["signal"] == "BUY"

    def test_no_json_returns_empty(self):
        assert _extract_json("No JSON here at all!") == {}

    def test_invalid_json_returns_empty(self):
        assert _extract_json("{broken: json}") == {}

    def test_empty_string(self):
        assert _extract_json("") == {}


# ── should_retry ─────────────────────────────────────────────────────────


class TestShouldRetry:
    def test_retries_on_error_below_limit(self):
        state = {"error": "LLM timeout", "retry_count": 0}
        assert should_retry(state) == "retry"

    def test_retries_on_error_at_one(self):
        state = {"error": "API error", "retry_count": 1}
        assert should_retry(state) == "retry"

    def test_stops_retrying_at_limit(self):
        state = {"error": "Still failing", "retry_count": 2}
        assert should_retry(state) == "continue"

    def test_continues_when_no_error(self):
        state = {"retry_count": 0}
        assert should_retry(state) == "continue"

    def test_continues_with_empty_error(self):
        state = {"error": None, "retry_count": 0}
        assert should_retry(state) == "continue"


# ── generate_signal ──────────────────────────────────────────────────────


class TestGenerateSignal:
    @pytest.mark.asyncio
    async def test_high_confidence_preserves_signal(self):
        state = {"final_signal": "BUY", "confidence": 0.80}
        result = await generate_signal(state)
        assert result["final_signal"] == "BUY"

    @pytest.mark.asyncio
    async def test_low_confidence_overrides_to_hold(self):
        state = {"final_signal": "BUY", "confidence": 0.50}
        result = await generate_signal(state)
        assert result["final_signal"] == "HOLD"

    @pytest.mark.asyncio
    async def test_boundary_confidence_below_threshold(self):
        state = {"final_signal": "SELL", "confidence": 0.64}
        result = await generate_signal(state)
        assert result["final_signal"] == "HOLD"

    @pytest.mark.asyncio
    async def test_boundary_confidence_at_threshold(self):
        state = {"final_signal": "SELL", "confidence": 0.65}
        result = await generate_signal(state)
        assert result["final_signal"] == "SELL"

    @pytest.mark.asyncio
    async def test_hold_stays_hold(self):
        state = {"final_signal": "HOLD", "confidence": 0.90}
        result = await generate_signal(state)
        assert result["final_signal"] == "HOLD"

    @pytest.mark.asyncio
    async def test_reasoning_includes_signal_info(self):
        state = {
            "final_signal": "BUY", "confidence": 0.80,
            "reasoning": "Strong technicals", "sentiment_score": 0.5,
        }
        result = await generate_signal(state)
        assert "BUY" in result["reasoning"]
        assert "80%" in result["reasoning"]


# ── Full Graph (mocked LLM) ─────────────────────────────────────────────


class TestBuildGraph:
    @pytest.mark.asyncio
    async def test_full_graph_with_mocked_llm(self):
        """Run the full graph with all LLM calls mocked."""
        mock_llm_response = {
            "content": '{"action": "BUY", "confidence": 0.8, "reasoning": "Test"}',
            "reasoning_details": None,
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }

        with patch("quantioa.llm.workflows.chat_with_reasoning", new_callable=AsyncMock) as mock_chat, \
             patch("quantioa.llm.workflows.chat_continuation", new_callable=AsyncMock) as mock_cont, \
             patch("quantioa.llm.workflows.sentiment_query", new_callable=AsyncMock) as mock_sentiment:

            mock_chat.return_value = mock_llm_response
            mock_cont.return_value = mock_llm_response
            mock_sentiment.return_value = '{"score": 0.5, "summary": "Neutral"}'

            graph = build_trading_decision_graph()

            initial_state = {
                "symbol": "TEST",
                "indicators": {"rsi": 55.0, "macd_hist": 0.01},
                "current_params": {"stop_loss_pct": 2.0},
                "recent_performance": {"win_rate": 0.55},
                "retry_count": 0,
            }

            result = await graph.ainvoke(initial_state)

            assert "final_signal" in result
            assert result["final_signal"] in ("BUY", "SELL", "HOLD")
            assert "confidence" in result

            # Verify LLM calls were made (chat_with_reasoning for optimize, chat_continuation for validate)
            total_llm_calls = mock_chat.call_count + mock_cont.call_count
            assert total_llm_calls >= 2
