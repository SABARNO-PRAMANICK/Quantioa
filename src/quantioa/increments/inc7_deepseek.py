"""
Increment 7: AI Parameter Optimization via Kimi K2.5 + LangGraph.

Replaces the original raw-httpx DeepSeek integration with:
- OpenAI SDK (pointed at OpenRouter)
- Kimi K2.5 with reasoning mode for chain-of-thought optimization
- LangGraph for multi-step decision workflows

This module provides both direct optimization and the full
LangGraph pipeline for production use.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from quantioa.llm.client import chat_with_reasoning
from quantioa.llm.workflows import TradingDecisionState, build_trading_decision_graph
from quantioa.prompts import optimization as opt_prompts

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """Result of AI-driven parameter optimization."""

    optimized_params: dict[str, float] = field(default_factory=dict)
    reasoning: str = ""
    confidence: float = 0.0
    signal: str = "HOLD"
    sentiment_score: float = 0.0
    raw_response: str = ""


class AIOptimizer:
    """AI-driven parameter optimization using Kimi K2.5 via LangGraph.

    Usage (simple):
        optimizer = AIOptimizer()
        result = await optimizer.optimize(current_params, performance)

    Usage (full pipeline):
        result = await optimizer.run_full_pipeline(
            symbol="NIFTY50",
            indicators={...},
            current_params={...},
            recent_performance={...},
        )
    """

    def __init__(self) -> None:
        self._graph = build_trading_decision_graph()
        self._optimization_history: list[OptimizationResult] = []

    async def optimize(
        self,
        current_params: dict[str, float],
        performance: dict[str, float],
    ) -> OptimizationResult:
        """Simple single-call optimization (no sentiment, no LangGraph).

        Good for quick parameter tuning checks.
        """
        try:
            response = await chat_with_reasoning(
                messages=[
                    {"role": "system", "content": opt_prompts.SYSTEM_SIMPLE},
                    {"role": "user", "content": opt_prompts.user_prompt_simple(current_params, performance)},
                ],
                enable_reasoning=True,
            )

            content = response["content"]
            parsed = self._extract_json(content)

            result = OptimizationResult(
                optimized_params=parsed.get("optimized_params", current_params),
                reasoning=parsed.get("reasoning", content),
                raw_response=content,
            )
            self._optimization_history.append(result)
            return result

        except Exception as e:
            logger.error("Simple optimization failed: %s", e)
            return OptimizationResult(
                optimized_params=current_params,
                reasoning=f"Optimization failed: {e}",
            )

    async def run_full_pipeline(
        self,
        symbol: str,
        indicators: dict[str, float],
        current_params: dict[str, float],
        recent_performance: dict[str, float],
    ) -> OptimizationResult:
        """Run the full LangGraph decision pipeline.

        Executes: analyze → optimize (Kimi K2.5 reasoning) → sentiment
        (Perplexity) → validate (continued reasoning) → signal.
        """
        initial_state: TradingDecisionState = {
            "symbol": symbol,
            "indicators": indicators,
            "current_params": current_params,
            "recent_performance": recent_performance,
            "retry_count": 0,
        }

        try:
            final_state = await self._graph.ainvoke(initial_state)

            result = OptimizationResult(
                optimized_params=final_state.get("optimized_params", current_params),
                reasoning=final_state.get("reasoning", ""),
                confidence=final_state.get("confidence", 0.0),
                signal=final_state.get("final_signal", "HOLD"),
                sentiment_score=final_state.get("sentiment_score", 0.0),
            )
            self._optimization_history.append(result)
            return result

        except Exception as e:
            logger.error("Full pipeline failed: %s", e)
            return OptimizationResult(
                optimized_params=current_params,
                reasoning=f"Pipeline failed: {e}",
                signal="HOLD",
            )

    @property
    def history(self) -> list[OptimizationResult]:
        return list(self._optimization_history)

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Best-effort JSON extraction from LLM output."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        brace_start = text.find("{")
        brace_end = text.rfind("}") + 1
        if brace_start >= 0 and brace_end > brace_start:
            try:
                return json.loads(text[brace_start:brace_end])
            except json.JSONDecodeError:
                pass
        return {}
