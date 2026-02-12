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
async def analyze_sentiment(symbol: str):
    """Get AI-powered sentiment analysis via Perplexity Sonar Pro."""
    from quantioa.llm.client import sentiment_query
    from quantioa.prompts import sentiment as sent_prompts

    result = await sentiment_query(
        prompt=sent_prompts.user_prompt_short(symbol),
        system_prompt=sent_prompts.SYSTEM_SHORT,
    )

    return {"symbol": symbol, "model": settings.perplexity_model, "analysis": result}


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
