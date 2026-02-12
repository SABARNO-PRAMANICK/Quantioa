"""
Sentiment analysis prompts — used by Perplexity Sonar Pro queries.

Covers:
- Node 3 (analyze_sentiment) in the LangGraph pipeline
- /sentiment/{symbol} endpoint in the AI service
"""

from __future__ import annotations

# ─── System Prompts ────────────────────────────────────────────────────────────

SYSTEM = (
    "You are a financial sentiment analyst specializing in Indian markets. "
    "Provide data-driven sentiment analysis based on current information. "
    "Always return valid JSON with 'score' and 'summary' keys."
)

SYSTEM_SHORT = "You are a financial sentiment analyst for Indian markets."


# ─── User Prompt Builders ─────────────────────────────────────────────────────


def user_prompt(symbol: str) -> str:
    """Build the user prompt for full sentiment analysis (LangGraph pipeline)."""
    return (
        f"Analyze the current market sentiment for {symbol} in the Indian stock market. "
        f"Consider recent news, institutional activity, global cues, and sector trends. "
        f"Rate sentiment from -1.0 (extremely bearish) to +1.0 (extremely bullish). "
        f"Return a JSON object with 'score' (float) and 'summary' (string)."
    )


def user_prompt_short(symbol: str) -> str:
    """Build a shorter user prompt for the /sentiment endpoint."""
    return (
        f"Analyze current market sentiment for {symbol} in the Indian stock market. "
        f"Consider news, institutional flows, and global cues. "
        f"Return JSON with 'score' (-1 to +1) and 'summary'."
    )
