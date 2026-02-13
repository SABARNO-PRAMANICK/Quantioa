"""
Sentiment Cache — Redis-backed with in-memory fallback.

Stores sentiment analysis results with a configurable TTL (default 6 hours).
If Redis is unavailable, falls back to an in-memory dict with expiry tracking
so dev/testing works without Redis running.

Usage:
    cache = SentimentCache()           # auto-connects to Redis or falls back
    cache = SentimentCache(redis_url="redis://localhost:6379/0")

    # Write (called by the sentiment service only)
    await cache.store("NIFTY50", {"score": 0.3, "summary": "Bullish on earnings"})

    # Read (called by trading agent)
    data = await cache.get("NIFTY50")  # returns dict or None
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Default TTL: 6 hours in seconds
DEFAULT_TTL = 6 * 60 * 60

_KEY_PREFIX = "quantioa:sentiment:"


class SentimentCache:
    """Redis-backed sentiment cache with in-memory fallback.

    The cache is intentionally simple:
    - Key: `quantioa:sentiment:{SYMBOL}` (e.g. `quantioa:sentiment:NIFTY50`)
    - Value: JSON string with sentiment data + metadata
    - TTL: 6 hours (configurable)
    """

    def __init__(
        self,
        redis_url: str | None = None,
        ttl: int = DEFAULT_TTL,
    ) -> None:
        self._ttl = ttl
        self._redis = None
        self._redis_url = redis_url
        # In-memory fallback: {key: (data_json, expiry_timestamp)}
        self._memory: dict[str, tuple[str, float]] = {}
        self._connected = False

    async def connect(self) -> None:
        """Try to connect to Redis. Falls back to in-memory if unavailable."""
        if self._redis_url:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(
                    self._redis_url,
                    decode_responses=True,
                    socket_connect_timeout=3,
                )
                await self._redis.ping()
                self._connected = True
                logger.info("Sentiment cache connected to Redis: %s", self._redis_url)
            except Exception as e:
                logger.warning(
                    "Redis unavailable (%s), using in-memory fallback", e
                )
                self._redis = None
                self._connected = False
        else:
            logger.info("No Redis URL configured, using in-memory sentiment cache")
            self._connected = False

    async def store(self, symbol: str, data: dict[str, Any]) -> None:
        """Store sentiment data for a symbol.

        Called by the sentiment service (NOT the trading agent).
        """
        key = _KEY_PREFIX + symbol.upper()
        payload = {
            **data,
            "_cached_at": time.time(),
            "_symbol": symbol.upper(),
        }
        payload_json = json.dumps(payload)

        if self._redis:
            try:
                await self._redis.setex(key, self._ttl, payload_json)
                logger.info("Cached sentiment for %s (TTL: %ds)", symbol, self._ttl)
                return
            except Exception as e:
                logger.warning("Redis store failed (%s), falling back to memory", e)

        # In-memory fallback
        expiry = time.time() + self._ttl
        self._memory[key] = (payload_json, expiry)
        logger.info("Cached sentiment for %s in memory (TTL: %ds)", symbol, self._ttl)

    async def get(self, symbol: str) -> dict[str, Any] | None:
        """Retrieve cached sentiment for a symbol.

        Returns None if not cached or expired.
        Called by the trading agent's sentiment reader.
        """
        key = _KEY_PREFIX + symbol.upper()

        if self._redis:
            try:
                raw = await self._redis.get(key)
                if raw:
                    return json.loads(raw)
                return None
            except Exception as e:
                logger.warning("Redis get failed (%s), trying memory", e)

        # In-memory fallback
        entry = self._memory.get(key)
        if entry is None:
            return None

        payload_json, expiry = entry
        if time.time() > expiry:
            del self._memory[key]
            return None

        return json.loads(payload_json)

    async def get_age_seconds(self, symbol: str) -> float | None:
        """How old is the cached sentiment? Returns None if no cache."""
        data = await self.get(symbol)
        if data and "_cached_at" in data:
            return time.time() - data["_cached_at"]
        return None

    async def clear(self, symbol: str) -> None:
        """Remove cached sentiment for a symbol."""
        key = _KEY_PREFIX + symbol.upper()
        if self._redis:
            try:
                await self._redis.delete(key)
            except Exception:
                pass
        self._memory.pop(key, None)

    @property
    def is_redis_connected(self) -> bool:
        return self._connected
