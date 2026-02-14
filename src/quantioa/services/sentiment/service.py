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
import json
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
        cache: SentimentCache | None = None,
        redis_url: str | None = None,
    ) -> None:
        self.symbols = symbols or DEFAULT_SYMBOLS
        self.interval_seconds = interval_hours * 3600

        if cache is not None:
            # Use the injected cache (e.g. from AI service's shared singleton)
            self.cache = cache
            self._owns_cache = False
        else:
            # Create our own cache (standalone mode)
            self.cache = SentimentCache(
                redis_url=redis_url or os.getenv("REDIS_URL") or settings.redis_url,
            )
            self._owns_cache = True

    async def start(self) -> None:
        """Connect cache and begin refresh loop."""
        if self._owns_cache:
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
        logger.info("Refreshing sentiment for %s via Perplexity...", symbol)

        try:
            raw = await sentiment_query(
                prompt=sent_prompts.user_prompt_short(symbol),
                system_prompt=sent_prompts.SYSTEM_SHORT,
            )

            logger.info(
                "Perplexity raw response for %s (%d chars): %s",
                symbol,
                len(raw),
                raw[:200],
            )

            # Try to parse structured JSON response
            parsed = self._parse_response(raw)

            # Ensure required fields with defaults
            data = {
                "score": float(parsed.get("score", 0.0)),
                "summary": str(parsed.get("summary", raw[:500])),
                "headlines": parsed.get("headlines", []),
                "confidence": float(parsed.get("confidence", 0.5)),
                "risks": parsed.get("risks", []),
                "catalysts": parsed.get("catalysts", []),
                "detailed_analysis": str(parsed.get("detailed_analysis", "")),
                "source": "perplexity_sonar_pro",
                "model": settings.perplexity_model,
            }

            await self.cache.store(symbol, data)
            logger.info(
                "✓ %s sentiment cached (score: %.2f, confidence: %.2f)",
                symbol,
                data["score"],
                data["confidence"],
            )
            return True

        except Exception as e:
            logger.error("✗ Failed to refresh %s: %s", symbol, e, exc_info=True)
            return False

    @staticmethod
    def _parse_response(raw: str) -> dict:
        """Parse the LLM response as JSON, handling common formatting issues."""
        if not raw or not isinstance(raw, str):
            return {"score": 0.0, "summary": str(raw), "confidence": 0.3}

        text = raw.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            # Remove opening fence (```json or ```)
            first_newline = text.index("\n") if "\n" in text else len(text)
            text = text[first_newline + 1 :]
            # Remove closing fence
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3].rstrip()

        # Try direct JSON parse
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass

        # Try to find JSON object in the text
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except (json.JSONDecodeError, TypeError):
                pass

        # Fallback: wrap raw text as summary
        logger.warning("Could not parse Perplexity response as JSON, wrapping as text")
        return {
            "score": 0.0,
            "summary": text[:500],
            "headlines": [],
            "confidence": 0.3,
        }

    async def refresh_once(self) -> None:
        """One-shot refresh (no loop)."""
        if self._owns_cache:
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
