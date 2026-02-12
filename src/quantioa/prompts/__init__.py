"""
Centralized prompt templates for all LLM calls.

All system prompts and user prompt templates live here so they can be
iterated on, versioned, and reviewed independently of business logic.

Usage:
    from quantioa.prompts import optimization, sentiment
    system = optimization.SYSTEM
    user   = optimization.user_prompt(params, analysis)
"""

from quantioa.prompts import optimization  # noqa: F401
from quantioa.prompts import sentiment  # noqa: F401
from quantioa.prompts import validation  # noqa: F401
