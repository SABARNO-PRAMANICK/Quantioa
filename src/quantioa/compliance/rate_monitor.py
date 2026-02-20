"""
Orders-Per-Second (OPS) rate monitor.

SEBI mandates that non-exchange-approved algos stay below 10 OPS.
This module tracks order rates per user and per algo, with configurable
thresholds and alerting.

Usage::

    from quantioa.compliance.rate_monitor import RateMonitor

    monitor = RateMonitor(max_ops=10)

    # Before placing each order:
    allowed = monitor.check_and_record(user_id, strategy_id="momentum_v1")
    if not allowed:
        # Reject order, log compliance violation
        ...

    # Periodic reporting:
    stats = monitor.get_stats(user_id)
    # {"current_ops": 3.2, "peak_ops": 7.1, "total_orders": 142}
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Default SEBI limit ───────────────────────────────────────────────────────
DEFAULT_MAX_OPS = 10  # Orders per second


@dataclass
class _OrderWindow:
    """Sliding window of order timestamps for a single entity."""

    timestamps: list[float] = field(default_factory=list)
    total_orders: int = 0
    peak_ops: float = 0.0
    violations: int = 0

    def record(self, now: float) -> float:
        """Record an order and return current OPS."""
        self.timestamps.append(now)
        self.total_orders += 1
        # Trim timestamps older than 1 second
        cutoff = now - 1.0
        self.timestamps = [t for t in self.timestamps if t > cutoff]
        current_ops = len(self.timestamps)
        if current_ops > self.peak_ops:
            self.peak_ops = current_ops
        return current_ops

    @property
    def current_ops(self) -> float:
        """Current OPS (orders in last 1 second)."""
        now = time.monotonic()
        cutoff = now - 1.0
        return sum(1 for t in self.timestamps if t > cutoff)


class RateMonitor:
    """Tracks order placement rates and enforces OPS limits.

    Operates at two levels:
    - **Per-user** (aggregate across all strategies)
    - **Per-strategy** within a user (for algo-level reporting)

    Thread-safe for single-threaded async (no locks needed in asyncio).
    """

    def __init__(self, max_ops: int = DEFAULT_MAX_OPS) -> None:
        self.max_ops = max_ops
        self._user_windows: dict[str, _OrderWindow] = defaultdict(_OrderWindow)
        self._strategy_windows: dict[str, _OrderWindow] = defaultdict(_OrderWindow)

    def check_and_record(
        self,
        user_id: str,
        *,
        strategy_id: str = "",
    ) -> bool:
        """Check OPS limit, record the order, and return whether it's allowed.

        Returns True if the order is within the OPS limit.
        Returns False if placing this order would exceed the limit.
        The order IS recorded even if rejected (for accurate violation tracking).
        """
        now = time.monotonic()

        # Per-user check
        user_key = str(user_id)
        user_ops = self._user_windows[user_key].record(now)

        # Per-strategy check (if provided)
        if strategy_id:
            strat_key = f"{user_key}:{strategy_id}"
            self._strategy_windows[strat_key].record(now)

        if user_ops > self.max_ops:
            self._user_windows[user_key].violations += 1
            logger.warning(
                "OPS LIMIT EXCEEDED: user=%s ops=%.1f limit=%d",
                user_id,
                user_ops,
                self.max_ops,
            )
            return False

        return True

    def get_user_stats(self, user_id: str) -> dict:
        """Get OPS statistics for a user."""
        user_key = str(user_id)
        window = self._user_windows.get(user_key)
        if not window:
            return {
                "current_ops": 0,
                "peak_ops": 0,
                "total_orders": 0,
                "violations": 0,
            }
        return {
            "current_ops": window.current_ops,
            "peak_ops": window.peak_ops,
            "total_orders": window.total_orders,
            "violations": window.violations,
        }

    def get_strategy_stats(self, user_id: str, strategy_id: str) -> dict:
        """Get OPS statistics for a specific strategy."""
        strat_key = f"{user_id}:{strategy_id}"
        window = self._strategy_windows.get(strat_key)
        if not window:
            return {"current_ops": 0, "peak_ops": 0, "total_orders": 0}
        return {
            "current_ops": window.current_ops,
            "peak_ops": window.peak_ops,
            "total_orders": window.total_orders,
        }

    def approaching_limit(self, user_id: str, threshold_pct: float = 0.8) -> bool:
        """Returns True if user is at >80% of OPS limit."""
        user_key = str(user_id)
        window = self._user_windows.get(user_key)
        if not window:
            return False
        return window.current_ops >= self.max_ops * threshold_pct

    def reset_user(self, user_id: str) -> None:
        """Reset tracking for a user (e.g. after a new trading day)."""
        user_key = str(user_id)
        self._user_windows.pop(user_key, None)
        # Also clear strategy windows for this user
        to_remove = [k for k in self._strategy_windows if k.startswith(f"{user_key}:")]
        for k in to_remove:
            del self._strategy_windows[k]


# Singleton
rate_monitor = RateMonitor()
