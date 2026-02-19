
from __future__ import annotations

import logging
import asyncio
from typing import Any

from quantioa.config import settings
from quantioa.models.types import Tick, Position, TradeSignal
from quantioa.llm.workflows import build_trading_decision_graph, TradingDecisionState
from quantioa.services.sentiment.cache import SentimentCache
from quantioa.services.sentiment.reader import SentimentReader

logger = logging.getLogger(__name__)

class AITradingStrategy:
    """Core AI Trading Strategy.
    
    Integrates:
    1. Market Data (Ticks/Indicators)
    2. Sentiment Analysis (Perplexity)
    3. Reasoning Engine (LangGraph + Kimi/OpenRouter)
    """

    def __init__(self, symbol: str, cache: SentimentCache | None = None):
        self.symbol = symbol
        self.graph = build_trading_decision_graph()
        
        # Initialize Sentiment components
        # We use a reader to access the cache populated by the separate SentimentService
        self.sentiment_cache = cache or SentimentCache()
        self.sentiment_reader = SentimentReader(self.sentiment_cache)
        
        self.latest_tick: Tick | None = None
        self.current_position: Position | None = None
        self.indicators: dict[str, float] = {}

    async def initialize(self):
        """Connect to resources."""
        await self.sentiment_cache.connect()
        logger.info("AITradingStrategy initialized for %s", self.symbol)

    async def on_tick(self, tick: Tick, indicators: dict[str, float], position: Position | None) -> dict[str, Any]:
        """Process a new market tick and generate a trading decision.
        
        Args:
            tick: Validated market tick.
            indicators: Computed technical indicators.
            position: Current position state (if any).
            
        Returns:
            Dict containing signal, confidence, and reasoning.
        """
        self.latest_tick = tick
        self.indicators = indicators
        self.current_position = position

        # Construct state for LangGraph
        state: TradingDecisionState = {
            "symbol": self.symbol,
            "indicators": indicators,
            "current_params": {
                "stop_loss_pct": settings.default_stop_loss_pct,
                "kelly_fraction": settings.default_kelly_fraction,
                "min_confidence": settings.min_confidence_threshold,
            },
            "recent_performance": {
                # TODO: Fetch real performance metrics from Analytics Service
                "win_rate": 0.55, 
                "sharpe_ratio": 1.1,
                "max_drawdown": 0.05,
                "total_trades": 20
            },
            "retry_count": 0
        }

        try:
            # Invoke the LangGraph workflow
            # The workflow internally handles:
            # - Parameter Optimization (Node 2)
            # - Sentiment Retrieval (Node 3)
            # - Validation (Node 4)
            # - Signal Generation (Node 5)
            result = await self.graph.ainvoke(state)
            
            signal = result.get("final_signal", "HOLD")
            confidence = result.get("confidence", 0.0)
            reasoning = result.get("reasoning", "")
            sentiment_score = result.get("sentiment_score", 0.0)
            
            logger.info(
                "AI Decision for %s: %s (Conf: %.2f, Sent: %.2f)", 
                self.symbol, signal, confidence, sentiment_score
            )
            
            return {
                "signal": signal,
                "confidence": confidence,
                "reasoning": reasoning,
                "sentiment_score": sentiment_score,
                "metadata": result.get("optimization_response", {})
            }

        except Exception as e:
            logger.error("Strategy execution failed: %s", e, exc_info=True)
            return {
                "signal": "HOLD",
                "confidence": 0.0,
                "reasoning": f"Strategy Error: {e}",
                "sentiment_score": 0.0
            }
