"""
Unit tests for the SentimentReader (read-only cache client).

Tests: neutral fallback, stale detection, normal reading.
"""

import time
import pytest
from unittest.mock import MagicMock, AsyncMock

from quantioa.services.sentiment.reader import SentimentReader, CachedSentiment


@pytest.fixture
def mock_cache():
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.get_age_seconds = AsyncMock(return_value=None)
    return cache


class TestNeutralFallback:
    @pytest.mark.asyncio
    async def test_returns_neutral_when_no_data(self, mock_cache):
        reader = SentimentReader(mock_cache)
        result = await reader.get_sentiment("NIFTY50")

        assert isinstance(result, CachedSentiment)
        assert result.available is False
        assert result.score == 0.0
        assert result.stale is True
        assert result.confidence == 0.0
        assert result.summary == "No sentiment data available"

    def test_neutral_factory(self):
        neutral = CachedSentiment.neutral("INFY")
        assert neutral.symbol == "INFY"
        assert neutral.available is False
        assert neutral.score == 0.0


class TestNormalReading:
    @pytest.mark.asyncio
    async def test_reads_cached_data(self, mock_cache):
        mock_cache.get.return_value = {
            "score": 0.7,
            "summary": "Strong bullish momentum",
            "confidence": 0.85,
            "headlines": ["Market rally continues"],
            "_cached_at": time.time() - 3600,
        }
        mock_cache.get_age_seconds.return_value = 3600.0  # 1 hour old

        reader = SentimentReader(mock_cache)
        result = await reader.get_sentiment("NIFTY50")

        assert result.available is True
        assert result.score == 0.7
        assert result.confidence == 0.85
        assert result.stale is False
        assert result.age_hours == 1.0
        assert len(result.headlines) == 1


class TestStaleDetection:
    @pytest.mark.asyncio
    async def test_marks_old_data_as_stale(self, mock_cache):
        mock_cache.get.return_value = {
            "score": 0.3,
            "summary": "Old data",
            "confidence": 0.5,
            "_cached_at": time.time() - 36000,  # 10 hours ago
        }
        mock_cache.get_age_seconds.return_value = 36000.0  # 10 hours

        reader = SentimentReader(mock_cache)
        result = await reader.get_sentiment("TEST")

        assert result.available is True
        assert result.stale is True
        assert result.age_hours == 10.0

    @pytest.mark.asyncio
    async def test_fresh_data_not_stale(self, mock_cache):
        mock_cache.get.return_value = {
            "score": 0.5, "summary": "Fresh", "confidence": 0.8,
            "_cached_at": time.time() - 600,
        }
        mock_cache.get_age_seconds.return_value = 600.0  # 10 minutes

        reader = SentimentReader(mock_cache)
        result = await reader.get_sentiment("TEST")

        assert result.stale is False
        assert result.age_hours == pytest.approx(0.2, abs=0.1)


class TestSymbolNormalization:
    @pytest.mark.asyncio
    async def test_symbol_uppercased(self, mock_cache):
        mock_cache.get.return_value = {
            "score": 0.0, "summary": "ok", "confidence": 0.5,
            "_cached_at": time.time(),
        }
        mock_cache.get_age_seconds.return_value = 0.0

        reader = SentimentReader(mock_cache)
        result = await reader.get_sentiment("nifty50")
        assert result.symbol == "NIFTY50"
