"""
Trade Confirmation Gate — multi-layer check before execution.

A signal must pass ALL gates before being allowed to execute.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from quantioa.engine.signal_generator import SignalOutput
from quantioa.models.enums import TradeSignal, VolatilityRegime

logger = logging.getLogger(__name__)


@dataclass
class ConfirmationResult:
    """Result of the trade confirmation check."""

    approved: bool
    signal: TradeSignal
    reasons: list[str]
    position_size_pct: float = 0.0  # % of capital to allocate

    def __str__(self) -> str:
        status = "APPROVED" if self.approved else "REJECTED"
        return f"[{status}] {self.signal.value} | {'; '.join(self.reasons)}"


class TradeConfirmation:
    """Multi-gate confirmation before trade execution.

    Gates:
    1. Minimum confidence threshold
    2. Non-HOLD signal
    3. Risk framework allows trading
    4. Regime-appropriate sizing

    Usage:
        gate = TradeConfirmation(min_confidence=0.5)
        result = gate.check(signal_output, risk_allowed=True)
        if result.approved:
            # execute trade
    """

    def __init__(
        self,
        min_confidence: float = 0.5,
        min_strength: float = 0.1,
        max_position_pct: float = 5.0,  # max % of capital per trade
    ) -> None:
        self._min_confidence = min_confidence
        self._min_strength = min_strength
        self._max_position_pct = max_position_pct

    def check(
        self,
        signal: SignalOutput,
        risk_allowed: bool = True,
        current_position_count: int = 0,
        max_positions: int = 5,
    ) -> ConfirmationResult:
        """Run all gates and return approval decision."""
        reasons: list[str] = []
        approved = True

        # Gate 1: Must not be HOLD
        if signal.signal == TradeSignal.HOLD:
            approved = False
            reasons.append("Signal is HOLD")

        # Gate 2: Minimum confidence
        if signal.confidence < self._min_confidence:
            approved = False
            reasons.append(f"Confidence {signal.confidence:.2f} < {self._min_confidence}")

        # Gate 3: Minimum strength
        if signal.strength < self._min_strength:
            approved = False
            reasons.append(f"Strength {signal.strength:.2f} < {self._min_strength}")

        # Gate 4: Risk framework
        if not risk_allowed:
            approved = False
            reasons.append("Risk framework halted trading")

        # Gate 5: Max positions
        if current_position_count >= max_positions:
            approved = False
            reasons.append(f"Max positions reached ({max_positions})")

        # Position size based on signal + regime
        position_pct = self._compute_size(signal) if approved else 0.0

        if approved:
            reasons.append(f"All gates passed → {position_pct:.1f}% allocation")

        return ConfirmationResult(
            approved=approved,
            signal=signal.signal,
            reasons=reasons,
            position_size_pct=round(position_pct, 2),
        )

    def _compute_size(self, signal: SignalOutput) -> float:
        """Determine position size as % of capital."""
        base = self._max_position_pct * signal.confidence

        # Regime adjustment
        regime_scale = {
            VolatilityRegime.EXTREME_LOW_VOL: 0.5,
            VolatilityRegime.LOW_VOL: 0.8,
            VolatilityRegime.NORMAL: 1.0,
            VolatilityRegime.HIGH_VOL: 0.6,
            VolatilityRegime.EXTREME_VOL: 0.3,
        }
        base *= regime_scale.get(signal.regime, 1.0)

        # Kelly bounds
        if signal.kelly_fraction > 0:
            base = min(base, signal.kelly_fraction * 100)

        return min(base, self._max_position_pct)
