"""
AI/LLM Service — orchestrates AI model calls via OpenRouter + LangGraph.

Models:
- Kimi K2.5 (moonshotai/kimi-k2.5) — primary AI with reasoning mode
- Perplexity Sonar Pro — sentiment analysis and news aggregation

Workflows:
- Parameter optimization (LangGraph pipeline)
- Sentiment analysis (Perplexity)
- Quick chat (single-turn Kimi K2.5)
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from quantioa.config import settings

app = FastAPI(title="Quantioa AI Service", version="0.1.0")


# ─── Request/Response Models ──────────────────────────────────────────────────


class OptimizationRequest(BaseModel):
    symbol: str = "NIFTY50"
    indicators: dict[str, float] = {}
    current_params: dict[str, float] = {}
    recent_performance: dict[str, float] = {}


class SentimentRequest(BaseModel):
    symbol: str
    include_news: bool = True


class ChatRequest(BaseModel):
    prompt: str
    system_prompt: str = ""
    enable_reasoning: bool = True


# ─── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "ai-service", "model": settings.ai_model}


@app.post("/optimize")
async def optimize_parameters(req: OptimizationRequest):
    """Run the full LangGraph optimization pipeline.

    Pipeline: analyze → optimize (Kimi K2.5 reasoning) → sentiment
    (Perplexity) → validate (continued reasoning) → signal.
    """
    from quantioa.increments.inc7_deepseek import AIOptimizer

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
    from quantioa.increments.inc7_deepseek import AIOptimizer

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
    """
    from quantioa.services.sentiment.cache import SentimentCache
    from quantioa.services.sentiment.reader import SentimentReader

    cache = SentimentCache(redis_url=None)
    await cache.connect()
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
    }


@app.post("/sentiment/{symbol}/refresh")
async def refresh_sentiment(symbol: str):
    """Admin endpoint: manually refresh sentiment for a symbol.

    This is the ONLY AI service endpoint that calls Perplexity.
    Should be called sparingly — the Sentiment Service handles
    automatic 6-hour refreshes.
    """
    from quantioa.services.sentiment.service import SentimentService

    service = SentimentService()
    await service.cache.connect()
    success = await service.refresh_symbol(symbol)

    if not success:
        raise HTTPException(status_code=502, detail="Sentiment refresh failed")

    return {"symbol": symbol, "status": "refreshed"}


@app.post("/chat")
async def chat(req: ChatRequest):
    """Direct chat with Kimi K2.5 (with optional reasoning)."""
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
