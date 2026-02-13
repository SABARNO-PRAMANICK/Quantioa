"""
Signal Generator — combines all indicators and increments into a final signal.

Weights:
- Technical indicators (40%): RSI, MACD, EMA crossovers
- Order flow / OFI (20%): Microstructure from Increment 1
- Volatility regime (15%): Regime multiplier from Increment 2
- Multi-timeframe agreement (15%): MTF score from Increment 3
- Kelly position suggestion (10%): Size suggestion from Increment 4
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from quantioa.models.enums import TradeSignal, VolatilityRegime

logger = logging.getLogger(__name__)


@dataclass
class SignalOutput:
    """Result of the signal generation pipeline."""

    signal: TradeSignal  # BUY / SELL / HOLD
    strength: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    technical_score: float = 0.0
    ofi_score: float = 0.0
    regime: VolatilityRegime = VolatilityRegime.NORMAL
    regime_multiplier: float = 1.0
    mtf_agreement: float = 0.0
    kelly_fraction: float = 0.0
    reasoning: str = ""
    recommended_stop_atr_mult: float = 2.0


class SignalGenerator:
    """Aggregates all signal sources into a final trading decision.

    Usage:
        gen = SignalGenerator()
        signal = gen.generate(indicators, ofi, regime_info, mtf, kelly)
    """

    # Weight allocation
    W_TECHNICAL = 0.40
    W_OFI = 0.20
    W_REGIME = 0.15
    W_MTF = 0.15
    W_KELLY = 0.10

    def generate(
        self,
        indicators: dict,
        ofi_result: dict | None = None,
        regime_result: dict | None = None,
        mtf_result: dict | None = None,
        kelly_result: dict | None = None,
    ) -> SignalOutput:
        """Generate a combined trading signal.

        Args:
            indicators: Dict from StreamingIndicatorSuite (RSI, MACD, EMA, etc.)
            ofi_result: Output from OrderFlowAnalyzer (signal_strength, direction)
            regime_result: Output from VolatilityRegimeDetector (regime, multiplier)
            mtf_result: Output from MultiTimeframeAnalyzer (agreement, direction)
            kelly_result: Output from KellyCriterionSizer (fraction, size)
        """
        ofi_result = ofi_result or {}
        regime_result = regime_result or {}
        mtf_result = mtf_result or {}
        kelly_result = kelly_result or {}

        # 1. Technical score from indicators
        tech_score = self._compute_technical_score(indicators)

        # 2. OFI score
        ofi_score = ofi_result.get("signal_strength", 0.0)
        ofi_direction = ofi_result.get("direction", 0)  # +1 or -1

        # 3. Regime
        regime_str = regime_result.get("regime", "NORMAL")
        try:
            regime = VolatilityRegime(regime_str)
        except ValueError:
            regime = VolatilityRegime.NORMAL
        regime_mult = regime_result.get("position_multiplier", 1.0)

        # 4. MTF agreement
        mtf_agreement = mtf_result.get("agreement_score", 0.0)
        mtf_direction = mtf_result.get("direction", 0)

        # 5. Kelly
        kelly_fraction = kelly_result.get("kelly_fraction", 0.0)

        # ─── Combined Score ────────────────────────────────────────────
        # Directional score: positive = BUY, negative = SELL
        tech_direction = 1.0 if tech_score > 0.5 else (-1.0 if tech_score < -0.5 else 0.0)

        combined = (
            self.W_TECHNICAL * tech_score
            + self.W_OFI * ofi_score * ofi_direction
            + self.W_MTF * mtf_agreement * mtf_direction
            + self.W_KELLY * min(kelly_fraction, 0.25)  # cap Kelly influence
        )

        # Regime adjustment
        combined *= regime_mult

        # ─── Signal Decision ───────────────────────────────────────────
        strength = abs(combined)
        confidence = min(strength * 1.5, 1.0)  # scale up for confidence

        if combined > 0.15:
            signal = TradeSignal.BUY
        elif combined < -0.15:
            signal = TradeSignal.SELL
        else:
            signal = TradeSignal.HOLD

        # MTF disagreement reduces confidence
        if mtf_agreement < 0.3 and signal != TradeSignal.HOLD:
            confidence *= 0.7

        reasoning = (
            f"Tech={tech_score:+.2f} OFI={ofi_score*ofi_direction:+.2f} "
            f"MTF={mtf_agreement:.1%} Regime={regime.value} "
            f"Kelly={kelly_fraction:.2f} → {signal.value} "
            f"(str={strength:.2f}, conf={confidence:.2f})"
        )

        return SignalOutput(
            signal=signal,
            strength=round(strength, 4),
            confidence=round(confidence, 4),
            technical_score=round(tech_score, 4),
            ofi_score=round(ofi_score, 4),
            regime=regime,
            regime_multiplier=regime_mult,
            mtf_agreement=round(mtf_agreement, 4),
            kelly_fraction=round(kelly_fraction, 4),
            reasoning=reasoning,
        )

    def _compute_technical_score(self, ind: dict) -> float:
        """Score from -1 to +1 based on indicator values."""
        score = 0.0
        n = 0

        # RSI
        rsi = ind.get("rsi", 50)
        if rsi < 30:
            score += 1.0  # oversold → buy signal
        elif rsi > 70:
            score -= 1.0  # overbought → sell signal
        else:
            score += (50 - rsi) / 50  # scaled between -0.4 and +0.4
        n += 1

        # MACD histogram
        macd_hist = ind.get("macd_hist", 0)
        if macd_hist > 0:
            score += min(macd_hist / 5.0, 1.0)
        else:
            score += max(macd_hist / 5.0, -1.0)
        n += 1

        # EMA crossover
        ema_9 = ind.get("ema_9", 0)
        ema_21 = ind.get("ema_21", 0)
        if ema_9 and ema_21:
            cross = (ema_9 - ema_21) / ema_21 * 100 if ema_21 else 0
            score += max(min(cross, 1.0), -1.0)
            n += 1

        # Price vs VWAP
        close = ind.get("close", 0)
        vwap = ind.get("vwap", 0)
        if close and vwap:
            vwap_diff = (close - vwap) / vwap * 100 if vwap else 0
            score += max(min(vwap_diff, 1.0), -1.0)
            n += 1

        return score / max(n, 1)
