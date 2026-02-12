"""
Validation prompts — used by the decision validation workflow node.

Covers:
- Node 4 (validate_decision) in the LangGraph pipeline
- Multi-turn reasoning continuation with Kimi K2.5
"""

from __future__ import annotations

# ─── System Prompts ────────────────────────────────────────────────────────────

SYSTEM = "You are a quantitative trading parameter optimizer."


# ─── User Prompt Builders ─────────────────────────────────────────────────────


def context_prompt(performance_analysis: str) -> str:
    """Build the initial context message for the validation chain."""
    return f"Parameters and performance: {performance_analysis}"


def followup_prompt(
    sentiment_score: float,
    sentiment_text: str,
) -> str:
    """Build the followup message that continues the reasoning chain.

    This is passed to chat_continuation() so Kimi K2.5 can validate
    its optimization suggestions against sentiment data.
    """
    return (
        f"Market sentiment is {sentiment_score:+.2f} ({sentiment_text}). "
        f"Given this sentiment data, validate your parameter suggestions. "
        f"Should we proceed with the optimization? "
        f"Return JSON with: 'signal' (BUY/SELL/HOLD), 'confidence' (0-1), "
        f"'reasoning' (string), and 'final_params' (dict)."
    )
