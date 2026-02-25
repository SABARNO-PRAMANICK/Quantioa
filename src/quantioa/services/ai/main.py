"""
AI/LLM Service — orchestrates AI model calls via OpenRouter + LangGraph.

Models:
- Primary AI model (configured via AI_MODEL env var) — with reasoning mode
- Perplexity Sonar Pro — sentiment analysis and news aggregation

Workflows:
- Parameter optimization (LangGraph pipeline)
- Sentiment analysis (Perplexity)
- Quick chat (single-turn with the configured model)
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from quantioa.config import settings
from quantioa.services.sentiment.cache import SentimentCache
from quantioa.services.sentiment.reader import SentimentReader

logger = logging.getLogger(__name__)


# ─── Shared State (module-level singletons) ──────────────────────────────────

_sentiment_cache: SentimentCache | None = None


def _get_redis_url() -> str | None:
    """Resolve Redis URL from env (Docker sets this) or settings."""
    return os.getenv("REDIS_URL") or settings.redis_url or None


async def get_sentiment_cache() -> SentimentCache:
    """Get or create the shared SentimentCache singleton."""
    global _sentiment_cache
    if _sentiment_cache is None:
        redis_url = _get_redis_url()
        _sentiment_cache = SentimentCache(redis_url=redis_url)
        await _sentiment_cache.connect()
        logger.info("Shared SentimentCache initialized (redis=%s)", redis_url)
    return _sentiment_cache


# ─── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize shared resources on startup."""
    await get_sentiment_cache()
    logger.info("AI Service started — model=%s", settings.ai_model)
    yield
    logger.info("AI Service shutting down")


app = FastAPI(title="Quantioa AI Service", version="0.1.0", lifespan=lifespan)


# ─── Request/Response Models ──────────────────────────────────────────────────


class OptimizationRequest(BaseModel):
    symbol: str = "NIFTY50"
    indicators: dict[str, float] = {}
    current_params: dict[str, float] = {}
    recent_performance: dict[str, float] = {}


class ChatRequest(BaseModel):
    prompt: str
    system_prompt: str = ""
    enable_reasoning: bool = True


# ─── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    cache = await get_sentiment_cache()
    return {
        "status": "healthy",
        "service": "ai-service",
        "model": settings.ai_model,
        "redis_connected": cache.is_redis_connected,
    }


@app.post("/optimize")
async def optimize_parameters(req: OptimizationRequest):
    """Run the full LangGraph optimization pipeline.

    Pipeline: analyze → optimize (AI reasoning) → sentiment
    (Perplexity) → validate (continued reasoning) → signal.
    """
    from quantioa.increments.inc7_ai_optimizer import AIOptimizer

    optimizer = AIOptimizer()
    result = await optimizer.run_full_pipeline(
        symbol=req.symbol,
        indicators=req.indicators,
        current_params=req.current_params,
        recent_performance=req.recent_performance,
    )

    return {
        "signal": result.signal,
        "confidence": result.confidence,
        "optimized_params": result.optimized_params,
        "reasoning": result.reasoning,
        "sentiment_score": result.sentiment_score,
    }


@app.post("/optimize/simple")
async def optimize_simple(req: OptimizationRequest):
    """Quick single-call optimization (no sentiment, no LangGraph)."""
    from quantioa.increments.inc7_ai_optimizer import AIOptimizer

    optimizer = AIOptimizer()
    result = await optimizer.optimize(
        current_params=req.current_params,
        performance=req.recent_performance,
    )

    return {
        "optimized_params": result.optimized_params,
        "reasoning": result.reasoning,
    }


@app.post("/sentiment/{symbol}")
async def get_sentiment(symbol: str):
    """Read cached sentiment for a symbol (from Redis/memory).

    The trading agent calls this endpoint — it NEVER calls Perplexity.
    Uses the shared SentimentCache singleton so data persists across requests.
    """
    cache = await get_sentiment_cache()
    reader = SentimentReader(cache)
    sentiment = await reader.get_sentiment(symbol)

    return {
        "symbol": symbol,
        "score": sentiment.score,
        "summary": sentiment.summary,
        "headlines": sentiment.headlines,
        "confidence": sentiment.confidence,
        "stale": sentiment.stale,
        "age_hours": sentiment.age_hours,
        "available": sentiment.available,
        "factors": {
            "domestic_macro": sentiment.factors.domestic_macro,
            "global_cues": sentiment.factors.global_cues,
            "sector_specific": sentiment.factors.sector_specific,
            "institutional_flows": sentiment.factors.institutional_flows,
            "technical_context": sentiment.factors.technical_context,
        },
        "risks": sentiment.risks,
        "catalysts": sentiment.catalysts,
    }


@app.post("/sentiment/{symbol}/refresh")
async def refresh_sentiment(symbol: str):
    """Admin endpoint: manually refresh sentiment for a symbol.

    Calls Perplexity Sonar Pro via OpenRouter, parses the JSON response,
    and stores it in the shared SentimentCache (Redis or in-memory).
    """
    from quantioa.services.sentiment.service import SentimentService

    cache = await get_sentiment_cache()
    service = SentimentService(cache=cache)
    success = await service.refresh_symbol(symbol)

    if not success:
        raise HTTPException(status_code=502, detail="Sentiment refresh failed")

    # Return the freshly cached data so the user can see it immediately
    reader = SentimentReader(cache)
    sentiment = await reader.get_sentiment(symbol)

    return {
        "symbol": symbol,
        "status": "refreshed",
        "sentiment": {
            "score": sentiment.score,
            "summary": sentiment.summary,
            "headlines": sentiment.headlines,
            "confidence": sentiment.confidence,
            "available": sentiment.available,
            "factors": {
                "domestic_macro": sentiment.factors.domestic_macro,
                "global_cues": sentiment.factors.global_cues,
                "sector_specific": sentiment.factors.sector_specific,
                "institutional_flows": sentiment.factors.institutional_flows,
                "technical_context": sentiment.factors.technical_context,
            },
        },
    }


@app.post("/chat")
async def chat(req: ChatRequest):
    """Direct chat with the configured AI model (with optional reasoning)."""
    from quantioa.llm.client import chat_with_reasoning

    messages = []
    if req.system_prompt:
        messages.append({"role": "system", "content": req.system_prompt})
    messages.append({"role": "user", "content": req.prompt})

    result = await chat_with_reasoning(
        messages=messages,
        enable_reasoning=req.enable_reasoning,
    )

    return {
        "content": result["content"],
        "model": result["model"],
        "usage": result["usage"],
        "has_reasoning": result.get("reasoning_details") is not None,
    }


@app.get("/models")
async def list_models():
    """List configured AI models."""
    return {
        "primary": {
            "model": settings.ai_model,
            "provider": "OpenRouter",
            "features": ["reasoning", "chain-of-thought", "multi-turn"],
        },
        "sentiment": {
            "model": settings.perplexity_model,
            "provider": "OpenRouter",
            "features": ["web-search", "news-aggregation"],
        },
    }
