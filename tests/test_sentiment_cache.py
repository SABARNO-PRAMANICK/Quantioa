"""
Unit tests for the SentimentCache (in-memory fallback mode).

Tests: store/get, TTL expiry, clear, age tracking, missing key.
"""

import time
import pytest

from quantioa.services.sentiment.cache import SentimentCache


@pytest.fixture
def cache():
    """In-memory-only cache (no Redis)."""
    return SentimentCache(redis_url=None, ttl=60)


class TestStoreAndGet:
    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, cache):
        await cache.connect()

        data = {"score": 0.8, "summary": "Bullish", "confidence": 0.9}
        await cache.store("NIFTY50", data)

        result = await cache.get("NIFTY50")

        assert result is not None
        assert result["score"] == 0.8
        assert result["summary"] == "Bullish"
        assert result["confidence"] == 0.9
        assert "_cached_at" in result

    @pytest.mark.asyncio
    async def test_case_insensitive_key(self, cache):
        await cache.connect()
        await cache.store("nifty50", {"score": 0.5})
        result = await cache.get("NIFTY50")
        assert result is not None
        assert result["score"] == 0.5

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, cache):
        await cache.connect()
        assert await cache.get("UNKNOWN") is None


class TestTTL:
    @pytest.mark.asyncio
    async def test_expired_entry_returns_none(self):
        cache = SentimentCache(redis_url=None, ttl=1)  # 1 second TTL
        await cache.connect()

        await cache.store("TEST", {"score": 0.5})

        # Manually set the expiry to past
        key = "quantioa:sentiment:TEST"
        json_str, _ = cache._memory[key]
        cache._memory[key] = (json_str, time.time() - 1)

        result = await cache.get("TEST")
        assert result is None


class TestAge:
    @pytest.mark.asyncio
    async def test_get_age_seconds(self, cache):
        await cache.connect()
        await cache.store("NIFTY50", {"score": 0.3})

        # Age should be very small (just stored)
        age = await cache.get_age_seconds("NIFTY50")
        assert age is not None
        assert 0 <= age < 2

    @pytest.mark.asyncio
    async def test_age_none_when_missing(self, cache):
        await cache.connect()
        assert await cache.get_age_seconds("UNKNOWN") is None


class TestClear:
    @pytest.mark.asyncio
    async def test_clear_removes_entry(self, cache):
        await cache.connect()
        await cache.store("INFY", {"score": 0.1})
        assert await cache.get("INFY") is not None

        await cache.clear("INFY")
        assert await cache.get("INFY") is None

    @pytest.mark.asyncio
    async def test_clear_nonexistent_no_error(self, cache):
        await cache.connect()
        await cache.clear("NONEXISTENT")  # Should not raise


class TestRedisStatus:
    def test_not_connected_without_redis(self, cache):
        assert cache.is_redis_connected is False

    @pytest.mark.asyncio
    async def test_connect_without_url_stays_memory(self, cache):
        await cache.connect()
        assert cache.is_redis_connected is False
