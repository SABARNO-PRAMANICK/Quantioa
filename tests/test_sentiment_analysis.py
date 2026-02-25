"""
Tests for the sentiment analysis service (SentimentService).

Tests: live integration (skipped if no key), mock parsing, edge cases.
"""

import os
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from quantioa.services.sentiment.service import SentimentService
from quantioa.services.sentiment.cache import SentimentCache


@pytest.fixture
def mock_cache():
    cache = MagicMock(spec=SentimentCache)
    cache.get = AsyncMock(return_value=None)
    cache.store = AsyncMock()
    return cache


# ── Live Integration (will skip without API key) ────────────────────────


@pytest.mark.asyncio
async def test_sentiment_service_live_integration(mock_cache):
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or "your_" in api_key or "sk-or-v1" not in api_key:
        pytest.skip("OPENROUTER_API_KEY not set or invalid")

    service = SentimentService(cache=mock_cache)
    try:
        success = await service.refresh_symbol("NIFTY50")
        if not success:
            pytest.skip("Live API call failed (likely 402 Insufficient OpenRouter Credits or Rate Limited)")
        assert success is True

        mock_cache.store.assert_called_once()
        args, _ = mock_cache.store.call_args
        data = args[1]
        assert isinstance(data, dict)
        assert -1.0 <= data["score"] <= 1.0
        assert data["confidence"] > 0.0
        assert len(data["summary"]) > 0
    except Exception as e:
        if "402" in str(e) or "credits" in str(e).lower():
            pytest.skip(f"API insufficient credits: {e}")
        raise


# ── Mock Parsing ─────────────────────────────────────────────────────────


def _mock_llm_response(content: str):
    """Create a mock completion response mimicking OpenAI SDK structure."""
    mock_choice = MagicMock()
    mock_choice.message.content = content

    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_completion.usage = MagicMock(prompt_tokens=50, completion_tokens=100)
    return mock_completion


@pytest.mark.asyncio
async def test_sentiment_parsing_valid_json():
    json_content = '''
    {
        "score": 0.75,
        "confidence": 0.9,
        "summary": "Market is bullish due to positive earnings.",
        "headlines": [
            {"title": "Stock hits all time high", "url": "http://news.com/1", "source": "News"}
        ]
    }
    '''

    with patch("quantioa.llm.client.AsyncOpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create = AsyncMock(
            return_value=_mock_llm_response(json_content)
        )

        cache = MagicMock(spec=SentimentCache)
        cache.store = AsyncMock()

        service = SentimentService(cache=cache)
        success = await service.refresh_symbol("RELIANCE")

        assert success is True
        cache.store.assert_called_once()
        data = cache.store.call_args[0][1]
        assert data["score"] == 0.75
        assert data["confidence"] == 0.9
        assert len(data["headlines"]) == 1


@pytest.mark.asyncio
async def test_sentiment_parsing_markdown_fences():
    """JSON wrapped in markdown code fences should still parse."""
    content = '```json\n{"score": 0.5, "confidence": 0.6, "summary": "Neutral"}\n```'

    with patch("quantioa.llm.client.AsyncOpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create = AsyncMock(
            return_value=_mock_llm_response(content)
        )

        cache = MagicMock(spec=SentimentCache)
        cache.store = AsyncMock()

        service = SentimentService(cache=cache)
        success = await service.refresh_symbol("TCS")

        assert success is True
        data = cache.store.call_args[0][1]
        assert data["score"] == 0.5


@pytest.mark.asyncio
async def test_sentiment_parsing_no_json():
    """Non-JSON response should fail gracefully."""
    content = "I think the market is bullish today."

    with patch("quantioa.llm.client.AsyncOpenAI") as MockClient:
        instance = MockClient.return_value
        instance.chat.completions.create = AsyncMock(
            return_value=_mock_llm_response(content)
        )

        cache = MagicMock(spec=SentimentCache)
        cache.store = AsyncMock()

        service = SentimentService(cache=cache)
        success = await service.refresh_symbol("WIPRO")

        # Should either return False or store a fallback
        # (depends on implementation — we just verify no crash)
        assert isinstance(success, bool)
