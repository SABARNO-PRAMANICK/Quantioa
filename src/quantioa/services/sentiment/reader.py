"""
Sentiment Reader — read-only client for the trading agent.

The trading agent uses this to read cached sentiment.
It NEVER calls Perplexity — only reads from Redis/memory cache.

Usage:
    reader = SentimentReader(cache)
    sentiment = await reader.get_sentiment("NIFTY50")
    # → {"score": 0.3, "summary": "...", "stale": False}
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from quantioa.services.sentiment.cache import SentimentCache

logger = logging.getLogger(__name__)

# If cache is older than this, mark as stale (but still usable)
STALE_THRESHOLD = 8 * 60 * 60  # 8 hours


@dataclass
class CachedSentiment:
    """Sentiment data as seen by the trading agent."""

    symbol: str
    score: float         # -1.0 to +1.0
    summary: str
    headlines: list[str]
    confidence: float    # 0.0 to 1.0
    stale: bool          # True if cache is older than 8hrs
    age_hours: float     # How old is this data
    available: bool      # False if no cached data exists

    @classmethod
    def neutral(cls, symbol: str) -> CachedSentiment:
        """Neutral fallback when no sentiment data is available."""
        return cls(
            symbol=symbol,
            score=0.0,
            summary="No sentiment data available",
            headlines=[],
            confidence=0.0,
            stale=True,
            age_hours=0.0,
            available=False,
        )


class SentimentReader:
    """Read-only sentiment client for the trading agent.

    This class NEVER calls Perplexity Sonar Pro.
    It only reads what the separate Sentiment Service has cached.
    """

    def __init__(self, cache: SentimentCache) -> None:
        self._cache = cache

    async def get_sentiment(self, symbol: str) -> CachedSentiment:
        """Get cached sentiment for a symbol.

        Returns neutral fallback if nothing is cached.
        """
        data = await self._cache.get(symbol)

        if data is None:
            logger.debug("No cached sentiment for %s, returning neutral", symbol)
            return CachedSentiment.neutral(symbol)

        age = await self._cache.get_age_seconds(symbol)
        age_hours = (age or 0) / 3600
        stale = age is not None and age > STALE_THRESHOLD

        if stale:
            logger.warning(
                "Sentiment for %s is stale (%.1f hrs old)", symbol, age_hours
            )

        return CachedSentiment(
            symbol=symbol.upper(),
            score=float(data.get("score", 0.0)),
            summary=str(data.get("summary", "")),
            headlines=data.get("headlines", []),
            confidence=float(data.get("confidence", 0.5)),
            stale=stale,
            age_hours=round(age_hours, 1),
            available=True,
        )
