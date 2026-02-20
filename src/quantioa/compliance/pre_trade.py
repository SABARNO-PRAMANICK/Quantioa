"""
Pre-trade compliance gate.

This is the single choke-point that validates ALL compliance checks
before any order reaches the broker. Call ``pre_trade_check()`` before
every order placement.

Checks performed (in order):
1. Kill switch (global → user → algo)
2. OPS rate limit (SEBI 10 orders/sec)
3. Algo registration (SEBI algo ID tagging)

Checks requiring DB (KYC, AI consent) should be performed at login /
session start — not on every tick. This gate covers only the
latency-sensitive, per-order checks.

Usage::

    from quantioa.compliance.pre_trade import pre_trade_check

    result = pre_trade_check(user_id="...", strategy_id="momentum_v1")
    if not result.allowed:
        logger.warning("Order blocked: %s", result.reason)
        return

    # Safe to proceed with order placement
    order = {"symbol": "RELIANCE", "side": "BUY", ...}
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from quantioa.compliance.algo_registry import algo_registry
from quantioa.compliance.kill_switch import kill_switch
from quantioa.compliance.rate_monitor import rate_monitor

logger = logging.getLogger(__name__)


@dataclass
class ComplianceResult:
    """Result of pre-trade compliance check."""

    allowed: bool
    reason: str = ""
    algo_id: str = ""


def pre_trade_check(
    user_id: str,
    *,
    strategy_id: str = "",
) -> ComplianceResult:
    """Run all pre-trade compliance checks.

    Returns ``ComplianceResult(allowed=True)`` if the order can proceed.
    Returns ``ComplianceResult(allowed=False, reason=...)`` if blocked.

    This function is designed to be called on EVERY order attempt.
    All checks are O(1) in-memory lookups — no DB or network calls.
    """
    # 1. Kill switch: global → user → algo
    if kill_switch.is_trading_halted(user_id=user_id, strategy_id=strategy_id):
        reason = kill_switch.get_halt_reason(
            user_id=user_id, strategy_id=strategy_id
        )
        logger.warning("Order BLOCKED by kill switch: user=%s reason=%s", user_id, reason)
        return ComplianceResult(allowed=False, reason=f"Kill switch active: {reason}")

    # 2. OPS rate limit
    if not rate_monitor.check_and_record(user_id, strategy_id=strategy_id):
        logger.warning("Order BLOCKED by OPS limit: user=%s", user_id)
        return ComplianceResult(
            allowed=False,
            reason=f"OPS limit exceeded ({rate_monitor.max_ops}/sec)",
        )

    # 3. Algo registration check
    algo_id = ""
    if strategy_id:
        algo_id = algo_registry.get_algo_id(strategy_id)
        if not algo_id:
            logger.warning(
                "Order BLOCKED: unregistered algo strategy=%s user=%s",
                strategy_id,
                user_id,
            )
            return ComplianceResult(
                allowed=False,
                reason=f"Strategy '{strategy_id}' not registered with exchange",
            )

        # Check if algo is active (not suspended)
        if not algo_registry.is_algo_active(strategy_id):
            logger.warning(
                "Order BLOCKED: suspended algo strategy=%s user=%s",
                strategy_id,
                user_id,
            )
            return ComplianceResult(
                allowed=False,
                reason=f"Strategy '{strategy_id}' is suspended",
            )

    return ComplianceResult(allowed=True, algo_id=algo_id)
