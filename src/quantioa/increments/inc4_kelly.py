"""
Increment 4: Kelly Criterion Position Sizing.

Calculates mathematically optimal position sizes based on historical
win rate and average win/loss ratio. Uses fractional Kelly (25%)
for safety.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass

from quantioa.config import settings
from quantioa.models.types import TradeResult


@dataclass(slots=True)
class KellyResult:
    """Output of Kelly Criterion calculation."""

    full_kelly: float            # Raw Kelly fraction
    fractional_kelly: float      # Safety-adjusted (25% of full)
    position_size_rupees: float  # How much capital to risk
    position_size_shares: int    # How many shares to buy
    win_rate: float
    avg_win: float
    avg_loss: float
    odds_ratio: float            # avg_win / avg_loss
    trades_analyzed: int
    is_active: bool              # False if < min trades for Kelly


class KellyCriterionSizer:
    """Position sizing using Kelly Criterion with fractional safety.

    Kelly Formula:
        f* = (b*p - q) / b
        where:
            b = odds = avg_win / avg_loss
            p = win rate
            q = 1 - p (loss rate)

    For safety, uses Fractional Kelly = f* × 0.25

    Example:
        Win rate: 52%, Avg win: ₹2,340, Avg loss: ₹1,850
        Odds: 1.265
        Kelly: (1.265 × 0.52 - 0.48) / 1.265 = 14.07%
        Fractional: 14.07% × 0.25 = 3.52%
        On ₹1,00,000: Risk ₹3,520 → 70 shares @ ₹50 risk

    Benefits:
        - Mathematically optimal (maximizes log growth)
        - Adaptive (adjusts as performance changes)
        - Prevents ruin (fractional Kelly limits exposure)
    """

    def __init__(
        self,
        kelly_fraction: float | None = None,
        min_trades: int | None = None,
        max_position_pct: float = 0.10,
        lookback: int = 100,
    ) -> None:
        self._kelly_fraction = kelly_fraction or settings.default_kelly_fraction
        self._min_trades = min_trades or settings.min_trade_history_for_kelly
        self._max_position_pct = max_position_pct  # Max 10% of capital per trade
        self._trades: collections.deque[TradeResult] = collections.deque(maxlen=lookback)

    def add_trade(self, trade: TradeResult) -> None:
        """Record a completed trade for Kelly calculation."""
        self._trades.append(trade)

    def add_trades(self, trades: list[TradeResult]) -> None:
        """Bulk-add historical trades."""
        for t in trades:
            self._trades.append(t)

    def calculate(
        self,
        capital: float,
        entry_price: float,
        stop_loss_price: float,
    ) -> KellyResult:
        """Calculate optimal position size.

        Args:
            capital: Total available capital (₹).
            entry_price: Expected entry price per share.
            stop_loss_price: Expected stop-loss level.

        Returns:
            KellyResult with position sizing details.
        """
        trades_count = len(self._trades)

        # Not enough history — use conservative default
        if trades_count < self._min_trades:
            default_risk = capital * 0.01  # 1% of capital
            risk_per_share = abs(entry_price - stop_loss_price) if stop_loss_price else entry_price * 0.02
            shares = int(default_risk / risk_per_share) if risk_per_share > 0 else 0

            return KellyResult(
                full_kelly=0.0,
                fractional_kelly=0.01,
                position_size_rupees=default_risk,
                position_size_shares=max(shares, 0),
                win_rate=0.5,
                avg_win=0.0,
                avg_loss=0.0,
                odds_ratio=1.0,
                trades_analyzed=trades_count,
                is_active=False,
            )

        # Calculate win rate and avg win/loss
        winners = [t for t in self._trades if t.is_winner]
        losers = [t for t in self._trades if not t.is_winner]

        win_rate = len(winners) / trades_count
        avg_win = sum(t.pnl for t in winners) / len(winners) if winners else 0.0
        avg_loss = abs(sum(t.pnl for t in losers) / len(losers)) if losers else 1.0

        # Odds ratio (b)
        odds = avg_win / avg_loss if avg_loss > 0 else 1.0

        # Kelly formula: f* = (b*p - q) / b
        q = 1.0 - win_rate
        full_kelly = (odds * win_rate - q) / odds if odds > 0 else 0.0
        full_kelly = max(full_kelly, 0.0)  # Never negative (means don't trade)

        # Fractional Kelly for safety
        fractional = full_kelly * self._kelly_fraction

        # Cap at max position percentage
        fractional = min(fractional, self._max_position_pct)

        # Convert to rupees and shares
        risk_amount = capital * fractional
        risk_per_share = abs(entry_price - stop_loss_price) if stop_loss_price else entry_price * 0.02
        shares = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0

        return KellyResult(
            full_kelly=full_kelly,
            fractional_kelly=fractional,
            position_size_rupees=risk_amount,
            position_size_shares=max(shares, 0),
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            odds_ratio=odds,
            trades_analyzed=trades_count,
            is_active=True,
        )

    @property
    def has_edge(self) -> bool:
        """True if current trade history shows a positive edge (Kelly > 0)."""
        if len(self._trades) < self._min_trades:
            return False
        winners = [t for t in self._trades if t.is_winner]
        losers = [t for t in self._trades if not t.is_winner]
        if not losers:
            return True
        win_rate = len(winners) / len(self._trades)
        avg_win = sum(t.pnl for t in winners) / len(winners) if winners else 0
        avg_loss = abs(sum(t.pnl for t in losers) / len(losers))
        odds = avg_win / avg_loss if avg_loss > 0 else 1.0
        kelly = (odds * win_rate - (1 - win_rate)) / odds
        return kelly > 0

    @property
    def trade_count(self) -> int:
        return len(self._trades)
