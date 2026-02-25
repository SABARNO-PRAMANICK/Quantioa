"""
Regime-aware sentiment weighting engine.

Sentiment factors (macro, global, sector, flows, technical) are weighted
differently depending on the current market volatility regime.

In extreme volatility, global/macro events dominate sentiment (flight-to-safety).
In calm markets, sector-specific news and institutional flows matter more.
"""

from __future__ import annotations

import logging

from quantioa.models.enums import VolatilityRegime
from quantioa.services.sentiment.reader import SentimentFactors

logger = logging.getLogger(__name__)


# ─── Weight Matrices ──────────────────────────────────────────────────────────

# Each row represents the relative weight of the 5 sentiment factors for a regime.
# Rows MUST sum to 1.0.
_REGIME_WEIGHTS: dict[VolatilityRegime, dict[str, float]] = {
    VolatilityRegime.EXTREME_LOW_VOL: {
        "domestic_macro": 0.10,
        "global_cues": 0.10,
        "sector_specific": 0.30,  # Dominates in calm markets
        "institutional_flows": 0.30,
        "technical_context": 0.20,
    },
    VolatilityRegime.LOW_VOL: {
        "domestic_macro": 0.15,
        "global_cues": 0.15,
        "sector_specific": 0.25,
        "institutional_flows": 0.25,
        "technical_context": 0.20,
    },
    VolatilityRegime.NORMAL: {
        "domestic_macro": 0.20,
        "global_cues": 0.20,
        "sector_specific": 0.20,
        "institutional_flows": 0.20,
        "technical_context": 0.20,
    },
    VolatilityRegime.HIGH_VOL: {
        "domestic_macro": 0.25,
        "global_cues": 0.30,  # Global panic/euphoria matters more
        "sector_specific": 0.10,
        "institutional_flows": 0.20,
        "technical_context": 0.15,
    },
    VolatilityRegime.EXTREME_VOL: {
        "domestic_macro": 0.30,
        "global_cues": 0.35,  # Dominates in extreme markets
        "sector_specific": 0.05,
        "institutional_flows": 0.15,
        "technical_context": 0.15,
    },
}

# The global influence of sentiment as a whole on the trading signal.
# During extreme volatility, sentiment/news is MORE important.
_SENTIMENT_INFLUENCE_MULTIPLIER: dict[VolatilityRegime, float] = {
    VolatilityRegime.EXTREME_LOW_VOL: 0.80,  # Dampen sentiment in quiet markets
    VolatilityRegime.LOW_VOL: 0.90,
    VolatilityRegime.NORMAL: 1.00,
    VolatilityRegime.HIGH_VOL: 1.10,         # Amplify sentiment
    VolatilityRegime.EXTREME_VOL: 1.20,      # News strongly drives extreme moves
}


class SentimentWeighter:
    """Computes regime-aware weighted sentiment scores."""

    @staticmethod
    def compute_weighted_score(
        factors: SentimentFactors, regime: VolatilityRegime
    ) -> float:
        """Compute a single score (-1.0 to +1.0) using regime-specific weights."""
        weights = _REGIME_WEIGHTS.get(regime, _REGIME_WEIGHTS[VolatilityRegime.NORMAL])

        weighted_sum = (
            factors.domestic_macro * weights["domestic_macro"]
            + factors.global_cues * weights["global_cues"]
            + factors.sector_specific * weights["sector_specific"]
            + factors.institutional_flows * weights["institutional_flows"]
            + factors.technical_context * weights["technical_context"]
        )

        # Cap between -1.0 and 1.0 just in case
        return float(max(-1.0, min(1.0, weighted_sum)))

    @staticmethod
    def get_influence_multiplier(regime: VolatilityRegime) -> float:
        """Get the global multiplier for how much sentiment matters overall."""
        return _SENTIMENT_INFLUENCE_MULTIPLIER.get(regime, 1.0)

    @staticmethod
    def compute_signal_contribution(
        factors: SentimentFactors, regime: VolatilityRegime
    ) -> tuple[float, float]:
        """Convenience method returning (weighted_score, influence_multiplier)."""
        score = SentimentWeighter.compute_weighted_score(factors, regime)
        mult = SentimentWeighter.get_influence_multiplier(regime)
        return score, mult
