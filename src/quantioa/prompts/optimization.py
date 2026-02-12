"""
Optimization prompts — used by the parameter optimization workflow.

Covers:
- Node 2 (optimize_parameters) in the LangGraph pipeline
- Simple single-call optimization in AIOptimizer.optimize()
"""

from __future__ import annotations

import json

# ─── System Prompts ────────────────────────────────────────────────────────────

SYSTEM = (
    "You are a quantitative trading parameter optimizer. "
    "Analyze the performance data and suggest specific parameter changes. "
    "Return a JSON object with 'optimized_params' (dict of param→value) "
    "and 'reasoning' (string explaining each change). "
    "Be conservative — only change parameters with clear evidence of improvement."
)

SYSTEM_SIMPLE = (
    "You are a quantitative trading parameter optimizer. "
    "Analyze performance and suggest parameter changes. "
    "Return valid JSON with 'optimized_params' and 'reasoning'."
)


# ─── User Prompt Builders ─────────────────────────────────────────────────────


def user_prompt(
    current_params: dict[str, float],
    performance_analysis: str,
) -> str:
    """Build the user prompt for full pipeline optimization."""
    return (
        f"Current parameters:\n{json.dumps(current_params, indent=2)}\n\n"
        f"Recent performance:\n{performance_analysis}\n\n"
        "Suggest optimized parameters. Return valid JSON."
    )


def user_prompt_simple(
    current_params: dict[str, float],
    performance: dict[str, float],
) -> str:
    """Build the user prompt for quick single-call optimization."""
    return (
        f"Current params: {json.dumps(current_params)}\n"
        f"Performance: {json.dumps(performance)}\n"
        "Suggest optimized parameters."
    )
