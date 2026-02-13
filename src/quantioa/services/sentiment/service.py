#!/usr/bin/env python3
"""
Sentiment Service — standalone process that refreshes sentiment on a schedule.

Runs independently from the trading agent. Calls Perplexity Sonar Pro
every N hours (default 6) and caches the results in Redis.

Run:
    # As a module
    python -m quantioa.services.sentiment.service

    # With custom interval
    SENTIMENT_INTERVAL_HOURS=4 python -m quantioa.services.sentiment.service

    # One-shot refresh (no loop)
    python -m quantioa.services.sentiment.service --once
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from quantioa.config import settings
from quantioa.llm.client import sentiment_query
from quantioa.prompts import sentiment as sent_prompts
from quantioa.services.sentiment.cache import SentimentCache

logger = logging.getLogger(__name__)

# Symbols to track sentiment for
DEFAULT_SYMBOLS = ["NIFTY50", "BANKNIFTY", "SENSEX"]


class SentimentService:
    """Standalone service that periodically refreshes sentiment cache.

    This is the ONLY component that calls Perplexity Sonar Pro.
    """

    def __init__(
        self,
        symbols: list[str] | None = None,
        interval_hours: float = 6.0,
        redis_url: str | None = None,
    ) -> None:
        self.symbols = symbols or DEFAULT_SYMBOLS
        self.interval_seconds = interval_hours * 3600
        self.cache = SentimentCache(
            redis_url=redis_url or os.getenv("REDIS_URL"),
        )

    async def start(self) -> None:
        """Connect cache and begin refresh loop."""
        await self.cache.connect()
        logger.info(
            "Sentiment Service started — tracking %s, refresh every %.0fh",
            self.symbols,
            self.interval_seconds / 3600,
        )

        while True:
            await self.refresh_all()
            logger.info(
                "Next refresh in %.0f hours", self.interval_seconds / 3600
            )
            await asyncio.sleep(self.interval_seconds)

    async def refresh_all(self) -> dict[str, bool]:
        """Refresh sentiment for all tracked symbols.

        Returns dict of {symbol: success}.
        """
        results = {}
        for symbol in self.symbols:
            success = await self.refresh_symbol(symbol)
            results[symbol] = success
            # Small delay between calls to avoid rate limiting
            await asyncio.sleep(2)

        succeeded = sum(1 for v in results.values() if v)
        logger.info(
            "Sentiment refresh complete: %d/%d succeeded",
            succeeded,
            len(results),
        )
        return results

    async def refresh_symbol(self, symbol: str) -> bool:
        """Call Perplexity and cache the result for one symbol."""
        logger.info("Refreshing sentiment for %s...", symbol)

        try:
            raw = await sentiment_query(
                prompt=sent_prompts.user_prompt(symbol),
                system_prompt=sent_prompts.SYSTEM,
            )

            # Try to parse structured response
            import json

            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                # Model returned free-text — wrap it
                parsed = {
                    "score": 0.0,
                    "summary": raw if isinstance(raw, str) else str(raw),
                    "headlines": [],
                    "confidence": 0.3,
                }

            # Ensure required fields
            data = {
                "score": float(parsed.get("score", 0.0)),
                "summary": str(parsed.get("summary", raw)),
                "headlines": parsed.get("headlines", []),
                "confidence": float(parsed.get("confidence", 0.5)),
                "source": "perplexity_sonar_pro",
                "model": settings.perplexity_model,
            }

            await self.cache.store(symbol, data)
            logger.info(
                "✓ %s sentiment cached (score: %.2f)", symbol, data["score"]
            )
            return True

        except Exception as e:
            logger.error("✗ Failed to refresh %s: %s", symbol, e)
            return False

    async def refresh_once(self) -> None:
        """One-shot refresh (no loop)."""
        await self.cache.connect()
        await self.refresh_all()


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    interval = float(os.getenv("SENTIMENT_INTERVAL_HOURS", "6"))
    symbols_env = os.getenv("SENTIMENT_SYMBOLS", "")
    symbols = [s.strip() for s in symbols_env.split(",") if s.strip()] or None

    service = SentimentService(
        symbols=symbols,
        interval_hours=interval,
        redis_url=os.getenv("REDIS_URL"),
    )

    if "--once" in sys.argv:
        print("Running one-shot sentiment refresh...")
        await service.refresh_once()
        print("Done.")
    else:
        print(f"Starting Sentiment Service (refresh every {interval}h)")
        await service.start()


if __name__ == "__main__":
    asyncio.run(main())
