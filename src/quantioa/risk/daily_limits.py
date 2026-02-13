"""
Daily P&L limit — halts trading when loss exceeds threshold.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class DailyLimitTracker:
    """Tracks daily P&L and halts trading at the configured loss limit.

    Usage:
        tracker = DailyLimitTracker(max_loss_pct=2.0, capital=100_000)
        tracker.record_pnl(pnl_amount)
        if not tracker.is_trading_allowed():
            # halt
    """

    def __init__(self, max_loss_pct: float = 2.0, capital: float = 100_000.0) -> None:
        self._max_loss_pct = max_loss_pct
        self._capital = capital
        self._max_loss_amount = capital * (max_loss_pct / 100.0)
        self._daily_pnl = 0.0
        self._halted = False

    def record_pnl(self, amount: float) -> None:
        """Record a realized P&L event."""
        self._daily_pnl += amount
        if self._daily_pnl <= -self._max_loss_amount:
            self._halted = True
            logger.warning(
                "DAILY LIMIT HIT: ₹%.0f loss (%.1f%% of ₹%.0f)",
                abs(self._daily_pnl), self._max_loss_pct, self._capital,
            )

    def is_trading_allowed(self) -> bool:
        return not self._halted

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl

    @property
    def remaining_loss_budget(self) -> float:
        return self._max_loss_amount + self._daily_pnl  # positive = room left

    def reset(self) -> None:
        """Reset for new trading day."""
        self._daily_pnl = 0.0
        self._halted = False
