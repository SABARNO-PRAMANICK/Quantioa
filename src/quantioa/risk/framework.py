"""
Unified Risk Framework — combines all risk layers into a single check.

Layers:
1. Position-level trailing stops (ATR-based)
2. Daily P&L limits
"""

from __future__ import annotations

import logging

from quantioa.risk.daily_limits import DailyLimitTracker
from quantioa.risk.position_risk import PositionRiskManager

logger = logging.getLogger(__name__)


class RiskFramework:
    """Orchestrates all risk layers.

    Usage:
        risk = RiskFramework(capital=100_000)
        risk.register_position("NIFTY50", "LONG", 22000, atr=150)

        # Each tick:
        stop_hit = risk.check_position("NIFTY50", current_price, atr)
        if stop_hit:
            # close position
            risk.record_trade_pnl(pnl)

        if not risk.is_trading_allowed():
            # halt new entries
    """

    def __init__(
        self,
        capital: float = 100_000.0,
        daily_loss_pct: float = 2.0,
        atr_multiplier: float = 2.0,
    ) -> None:
        self.positions = PositionRiskManager(atr_multiplier=atr_multiplier)
        self.daily = DailyLimitTracker(max_loss_pct=daily_loss_pct, capital=capital)

    def register_position(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        atr: float,
    ) -> None:
        self.positions.register_position(symbol, side, entry_price, atr)

    def check_position(
        self,
        symbol: str,
        current_price: float,
        atr: float,
    ) -> bool:
        """Returns True if stop is hit and position should be closed."""
        return self.positions.update(symbol, current_price, atr)

    def record_trade_pnl(self, pnl: float) -> None:
        self.daily.record_pnl(pnl)

    def close_position(self, symbol: str) -> None:
        self.positions.remove(symbol)

    def is_trading_allowed(self) -> bool:
        return self.daily.is_trading_allowed()

    @property
    def daily_pnl(self) -> float:
        return self.daily.daily_pnl
