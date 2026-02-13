"""
Position-level risk management — ATR-based trailing stops.

Each open position gets a trailing stop that adjusts with ATR.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StopLevel:
    """Tracks stop-loss for a single position."""

    symbol: str
    side: str  # "LONG" or "SHORT"
    entry_price: float
    stop_price: float
    atr_multiplier: float = 2.0
    highest_since_entry: float = 0.0
    lowest_since_entry: float = float("inf")


class PositionRiskManager:
    """Manages ATR-based trailing stops for all open positions.

    For LONG: stop = highest_price - atr * multiplier
    For SHORT: stop = lowest_price + atr * multiplier
    """

    def __init__(self, atr_multiplier: float = 2.0) -> None:
        self._atr_multiplier = atr_multiplier
        self._stops: dict[str, StopLevel] = {}

    def register_position(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        atr: float,
    ) -> StopLevel:
        """Register a new position and set initial stop."""
        if side == "LONG":
            stop = entry_price - atr * self._atr_multiplier
        else:
            stop = entry_price + atr * self._atr_multiplier

        sl = StopLevel(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            stop_price=round(stop, 2),
            atr_multiplier=self._atr_multiplier,
            highest_since_entry=entry_price,
            lowest_since_entry=entry_price,
        )
        self._stops[symbol] = sl
        logger.info("Stop set for %s %s: ₹%.2f", side, symbol, stop)
        return sl

    def update(self, symbol: str, current_price: float, atr: float) -> bool:
        """Update trailing stop. Returns True if stop is hit."""
        sl = self._stops.get(symbol)
        if not sl:
            return False

        if sl.side == "LONG":
            sl.highest_since_entry = max(sl.highest_since_entry, current_price)
            new_stop = sl.highest_since_entry - atr * sl.atr_multiplier
            sl.stop_price = max(sl.stop_price, round(new_stop, 2))  # only trail up
            return current_price <= sl.stop_price
        else:
            sl.lowest_since_entry = min(sl.lowest_since_entry, current_price)
            new_stop = sl.lowest_since_entry + atr * sl.atr_multiplier
            sl.stop_price = min(sl.stop_price, round(new_stop, 2))  # only trail down
            return current_price >= sl.stop_price

    def remove(self, symbol: str) -> None:
        self._stops.pop(symbol, None)

    def get_stop(self, symbol: str) -> float | None:
        sl = self._stops.get(symbol)
        return sl.stop_price if sl else None
