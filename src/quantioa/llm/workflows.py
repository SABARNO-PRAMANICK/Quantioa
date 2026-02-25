"""
LangGraph Trading Decision Workflow.

Models the AI-augmented trading decision pipeline as a stateful graph:

    ┌──────────────┐
    │ Analyze      │ ← Indicators + market data
    │ Performance  │
    └──────┬───────┘
           │
    ┌──────▼───────┐
    │  Optimize    │ ← AI model with reasoning
    │  Parameters  │
    └──────┬───────┘
           │
    ┌──────▼───────┐
    │  Sentiment   │ ← Perplexity Sonar Pro
    │  Analysis    │
    └──────┬───────┘
           │
    ┌──────▼───────┐
    │  Validate    │ ← AI model (continued reasoning)
    │  Decision    │
    └──────┬───────┘
           │
    ┌──────▼───────┐
    │  Generate    │ ← Final signal + explanation
    │  Signal      │
    └──────────────┘

Each node processes the shared state and passes it forward.
Conditional edges handle retries and fallbacks.
"""

from __future__ import annotations

import json
import logging
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from quantioa.llm.client import chat_continuation, chat_with_reasoning, sentiment_query
from quantioa.prompts import optimization as opt_prompts
from quantioa.prompts import sentiment as sent_prompts
from quantioa.prompts import validation as val_prompts

logger = logging.getLogger(__name__)


# ─── State Schema ──────────────────────────────────────────────────────────────


class TradingDecisionState(TypedDict, total=False):
    """State passed between LangGraph nodes."""

    # Input
    symbol: str
    indicators: dict[str, float]
    current_params: dict[str, float]
    recent_performance: dict[str, float]

    # Node outputs
    performance_analysis: str
    optimization_response: dict[str, Any]
    optimized_params: dict[str, float]
    sentiment_text: str
    sentiment_score: float
    validation_response: dict[str, Any]
    final_signal: str
    confidence: float
    reasoning: str

    # Control
    error: str | None
    retry_count: int


# ─── Node Functions ────────────────────────────────────────────────────────────


async def analyze_performance(state: TradingDecisionState) -> TradingDecisionState:
    """Node 1: Analyze recent trading performance.

    Summarizes key metrics (win rate, Sharpe, drawdown) into a
    human-readable analysis for the optimizer.
    """
    perf = state.get("recent_performance", {})
    indicators = state.get("indicators", {})

    analysis = (
        f"Symbol: {state.get('symbol', 'UNKNOWN')}\n"
        f"Win Rate: {perf.get('win_rate', 0):.1%}\n"
        f"Sharpe Ratio: {perf.get('sharpe_ratio', 0):.2f}\n"
        f"Max Drawdown: {perf.get('max_drawdown', 0):.1%}\n"
        f"Avg Win/Loss Ratio: {perf.get('avg_win_loss_ratio', 0):.2f}\n"
        f"Total Trades: {perf.get('total_trades', 0)}\n"
        f"RSI: {indicators.get('rsi', 50):.1f}\n"
        f"ATR: {indicators.get('atr', 0):.4f}\n"
        f"MACD Histogram: {indicators.get('macd_hist', 0):.4f}\n"
    )

    return {**state, "performance_analysis": analysis}


async def optimize_parameters(state: TradingDecisionState) -> TradingDecisionState:
    """Node 2: Ask the configured AI model to suggest parameter optimizations.

    Uses reasoning mode so the model shows its chain-of-thought
    about why specific parameter changes would improve performance.
    """
    current_params = state.get("current_params", {})
    analysis = state.get("performance_analysis", "")

    try:
        response = await chat_with_reasoning(
            messages=[
                {"role": "system", "content": opt_prompts.SYSTEM},
                {"role": "user", "content": opt_prompts.user_prompt(current_params, analysis)},
            ],
            enable_reasoning=True,
        )

        # Try to parse JSON from response
        content = response["content"]
        optimized = _extract_json(content)

        return {
            **state,
            "optimization_response": response,
            "optimized_params": optimized.get("optimized_params", current_params),
        }
    except Exception as e:
        logger.error("Parameter optimization failed: %s", e)
        return {
            **state,
            "optimization_response": {},
            "optimized_params": current_params,
            "error": f"Optimization failed: {e}",
        }


async def analyze_sentiment(state: TradingDecisionState) -> TradingDecisionState:
    """Node 3: Read cached market sentiment (from Redis/memory).

    The trading agent NEVER calls Perplexity Sonar Pro directly.
    It reads whatever the separate Sentiment Service has cached.
    If no cached sentiment exists, returns neutral values.
    """
    symbol = state.get("symbol", "NIFTY50")

    try:
        from quantioa.services.sentiment.cache import SentimentCache
        from quantioa.services.sentiment.reader import SentimentReader
        from quantioa.config import settings

        cache = SentimentCache(redis_url=settings.redis_url)  # use correct redis URL
        await cache.connect()
        reader = SentimentReader(cache)
        sentiment = await reader.get_sentiment(symbol)

        if sentiment.available:
            logger.info(
                "Using cached sentiment for %s (score=%.2f, age=%.1fh, stale=%s)",
                symbol, sentiment.score, sentiment.age_hours, sentiment.stale,
            )
        else:
            logger.info("No cached sentiment for %s, using neutral", symbol)

        return {
            **state,
            "sentiment_text": sentiment.summary,
            "sentiment_score": sentiment.score,
            "sentiment_factors": {
                "domestic_macro": sentiment.factors.domestic_macro,
                "global_cues": sentiment.factors.global_cues,
                "sector_specific": sentiment.factors.sector_specific,
                "institutional_flows": sentiment.factors.institutional_flows,
                "technical_context": sentiment.factors.technical_context,
            }
        }
    except Exception as e:
        logger.error("Sentiment cache read failed: %s", e)
        return {
            **state,
            "sentiment_text": "Sentiment analysis unavailable",
            "sentiment_score": 0.0,
            "error": f"Sentiment cache read failed: {e}",
        }


async def validate_decision(state: TradingDecisionState) -> TradingDecisionState:
    """Node 4: Validate the optimization with continued reasoning.

    Uses chat_continuation to have the AI model review its own
    parameter suggestions against the sentiment data — the model
    continues reasoning from where it left off.
    """
    opt_response = state.get("optimization_response", {})
    sentiment_score = state.get("sentiment_score", 0.0)
    sentiment_text = state.get("sentiment_text", "")

    if not opt_response:
        return {
            **state,
            "validation_response": {},
            "final_signal": "HOLD",
            "confidence": 0.0,
            "reasoning": "No optimization data available",
        }

    followup = val_prompts.followup_prompt(sentiment_score, sentiment_text)

    try:
        initial_messages = [
            {"role": "system", "content": val_prompts.SYSTEM},
            {"role": "user", "content": val_prompts.context_prompt(state.get('performance_analysis', ''))},
        ]

        response = await chat_continuation(
            initial_messages=initial_messages,
            followup=followup,
            previous_response=opt_response,
        )

        parsed = _extract_json(response["content"])

        return {
            **state,
            "validation_response": response,
            "final_signal": parsed.get("signal", "HOLD"),
            "confidence": float(parsed.get("confidence", 0.5)),
            "reasoning": parsed.get("reasoning", response["content"]),
        }
    except Exception as e:
        logger.error("Decision validation failed: %s", e)
        return {
            **state,
            "validation_response": {},
            "final_signal": "HOLD",
            "confidence": 0.3,
            "reasoning": f"Validation failed, defaulting to HOLD: {e}",
        }


async def generate_signal(state: TradingDecisionState) -> TradingDecisionState:
    """Node 5: Produce the final trading signal.

    Combines the AI reasoning with a confidence threshold check.
    """
    signal = state.get("final_signal", "HOLD")
    confidence = state.get("confidence", 0.0)

    # Apply confidence threshold
    if confidence < 0.65:
        signal = "HOLD"

    reasoning = state.get("reasoning", "")
    sentiment = state.get("sentiment_score", 0.0)

    full_reasoning = (
        f"Signal: {signal} (confidence: {confidence:.0%})\n"
        f"Sentiment: {sentiment:+.2f}\n"
        f"AI Reasoning: {reasoning}"
    )

    return {
        **state,
        "final_signal": signal,
        "confidence": confidence,
        "reasoning": full_reasoning,
    }


# ─── Conditional Routing ──────────────────────────────────────────────────────


def should_retry(state: TradingDecisionState) -> str:
    """Decide whether to retry optimization on error."""
    error = state.get("error")
    retry_count = state.get("retry_count", 0)

    if error and retry_count < 2:
        return "retry"
    return "continue"


# ─── Graph Construction ───────────────────────────────────────────────────────


def build_trading_decision_graph() -> StateGraph:
    """Build the LangGraph trading decision workflow.

    Returns a compiled graph that can be invoked with:
        result = await graph.ainvoke(initial_state)
    """
    graph = StateGraph(TradingDecisionState)

    # Add nodes
    graph.add_node("analyze_performance", analyze_performance)
    graph.add_node("optimize_parameters", optimize_parameters)
    graph.add_node("analyze_sentiment", analyze_sentiment)
    graph.add_node("validate_decision", validate_decision)
    graph.add_node("generate_signal", generate_signal)

    # Define edges (linear flow with conditional retry)
    graph.set_entry_point("analyze_performance")
    graph.add_edge("analyze_performance", "optimize_parameters")

    graph.add_conditional_edges(
        "optimize_parameters",
        should_retry,
        {
            "retry": "optimize_parameters",
            "continue": "analyze_sentiment",
        },
    )

    graph.add_edge("analyze_sentiment", "validate_decision")
    graph.add_edge("validate_decision", "generate_signal")
    graph.add_edge("generate_signal", END)

    return graph.compile()


# ─── Helpers ───────────────────────────────────────────────────────────────────


def _extract_json(text: str) -> dict:
    """Best-effort JSON extraction from LLM response text."""
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON block in markdown
    for marker in ("```json", "```"):
        if marker in text:
            start = text.index(marker) + len(marker)
            end = text.index("```", start)
            try:
                return json.loads(text[start:end].strip())
            except (json.JSONDecodeError, ValueError):
                pass

    # Try to find JSON object in text
    brace_start = text.find("{")
    brace_end = text.rfind("}") + 1
    if brace_start >= 0 and brace_end > brace_start:
        try:
            return json.loads(text[brace_start:brace_end])
        except json.JSONDecodeError:
            pass

    return {}
