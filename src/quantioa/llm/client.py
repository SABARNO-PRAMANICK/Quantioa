"""
LLM client — OpenAI SDK wrapper for OpenRouter.

Uses the openai SDK with base_url pointed at OpenRouter.
Supports Kimi K2.5 reasoning mode with chain-of-thought continuation.
"""

from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

from quantioa.config import settings

logger = logging.getLogger(__name__)


def get_openrouter_client() -> AsyncOpenAI:
    """Create an async OpenAI client pointed at OpenRouter."""
    return AsyncOpenAI(
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
    )


async def chat_with_reasoning(
    messages: list[dict[str, Any]],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    enable_reasoning: bool = True,
) -> dict[str, Any]:
    """Call Kimi K2.5 with reasoning enabled.

    Supports multi-turn reasoning continuation by preserving
    `reasoning_details` in the assistant message.

    Args:
        messages: Chat messages (user/assistant/system).
        model: Override default model.
        temperature: Sampling temperature.
        max_tokens: Max output tokens.
        enable_reasoning: Whether to enable chain-of-thought reasoning.

    Returns:
        Dict with 'content', 'reasoning_details', and full 'message'.
    """
    client = get_openrouter_client()
    model = model or settings.ai_model

    extra_body = {}
    if enable_reasoning:
        extra_body["reasoning"] = {"enabled": True}

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body if extra_body else None,
        )

        msg = response.choices[0].message

        return {
            "content": msg.content or "",
            "reasoning_details": getattr(msg, "reasoning_details", None),
            "message": msg,
            "model": model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        }
    except Exception as e:
        logger.error("LLM call failed (model=%s): %s", model, e)
        raise


async def chat_simple(
    prompt: str,
    system_prompt: str = "",
    model: str | None = None,
    temperature: float = 0.7,
) -> str:
    """Simple single-turn chat — returns content string only."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    result = await chat_with_reasoning(
        messages=messages,
        model=model,
        temperature=temperature,
        enable_reasoning=False,
    )
    return result["content"]


async def chat_continuation(
    initial_messages: list[dict[str, Any]],
    followup: str,
    previous_response: dict[str, Any],
    model: str | None = None,
) -> dict[str, Any]:
    """Continue a reasoning chain by preserving reasoning_details.

    This is the Kimi K2.5-specific feature where the model can
    continue reasoning from where it left off.

    Args:
        initial_messages: Original conversation messages.
        followup: New user message to continue with.
        previous_response: The dict returned from a prior chat_with_reasoning call.
        model: Override model.

    Returns:
        New response dict with continued reasoning.
    """
    messages = list(initial_messages)

    # Preserve the assistant message with reasoning_details
    messages.append({
        "role": "assistant",
        "content": previous_response["content"],
        "reasoning_details": previous_response.get("reasoning_details"),
    })

    # Add the followup
    messages.append({"role": "user", "content": followup})

    return await chat_with_reasoning(
        messages=messages,
        model=model,
        enable_reasoning=True,
    )


async def sentiment_query(
    prompt: str,
    system_prompt: str = "",
) -> str:
    """Query Perplexity Sonar Pro for sentiment / news analysis."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    result = await chat_with_reasoning(
        messages=messages,
        model=settings.perplexity_model,
        enable_reasoning=False,
        temperature=0.3,
    )
    return result["content"]
