"""
Tests for Regime-Aware Sentiment Weighting Engine.
"""

from quantioa.models.enums import VolatilityRegime
from quantioa.services.sentiment.reader import SentimentFactors
from quantioa.services.sentiment.sentiment_weights import (
    _REGIME_WEIGHTS,
    SentimentWeighter,
)


def test_weights_sum_to_one():
    """Verify all regime weight matrices sum to 1.0 (or very close)."""
    for regime, weights in _REGIME_WEIGHTS.items():
        total = sum(weights.values())
        assert abs(total - 1.0) < 1e-6, f"Regime {regime} weights sum to {total} != 1.0"


def test_weighter_computes_correct_score():
    """Verify that specific factors are weighted correctly."""
    # Let's use NORMAL baseline. All weights are 0.20
    # factors: macro=1.0, global=0.5, sector=-0.5, flows=0, tech=1.0
    factors = SentimentFactors(
        domestic_macro=1.0,
        global_cues=0.5,
        sector_specific=-0.5,
        institutional_flows=0.0,
        technical_context=1.0,
    )

    # Expected: (1.0*0.2) + (0.5*0.2) + (-0.5*0.2) + (0*0.2) + (1.0*0.2)
    # = 0.2 + 0.1 - 0.1 + 0 + 0.2 = 0.4
    score = SentimentWeighter.compute_weighted_score(factors, VolatilityRegime.NORMAL)
    assert abs(score - 0.4) < 1e-6


def test_extreme_regime_amplifies_global_macro():
    """Verify that EXTREME_VOL puts high weight on macro/global cues."""
    factors = SentimentFactors(
        domestic_macro=1.0,
        global_cues=1.0,
        sector_specific=-1.0,  # Negative sector sentiment should be buried by panic context
        institutional_flows=-1.0,
        technical_context=-1.0,
    )

    # In EXTREME_VOL: macro(0.3) + global(0.35) = 0.65 positive
    # Negative: sector(0.05) + flows(0.15) + tech(0.15) = 0.35 negative
    # Expected net: 0.65 - 0.35 = 0.30 positive
    score = SentimentWeighter.compute_weighted_score(factors, VolatilityRegime.EXTREME_VOL)
    assert abs(score - 0.30) < 1e-6

    # In EXTREME_LOW_VOL (Calm): macro(0.1) + global(0.1) = 0.20 positive
    # Negative: sector(0.3) + flows(0.3) + tech(0.2) = 0.80 negative
    # Expected net: 0.20 - 0.80 = -0.60 negative
    score2 = SentimentWeighter.compute_weighted_score(factors, VolatilityRegime.EXTREME_LOW_VOL)
    assert abs(score2 - (-0.60)) < 1e-6


def test_influence_multiplier():
    assert SentimentWeighter.get_influence_multiplier(VolatilityRegime.NORMAL) == 1.0
    assert SentimentWeighter.get_influence_multiplier(VolatilityRegime.EXTREME_VOL) == 1.20
    assert SentimentWeighter.get_influence_multiplier(VolatilityRegime.EXTREME_LOW_VOL) == 0.80

    # Test the convenience method
    factors = SentimentFactors.neutral()
    score, mult = SentimentWeighter.compute_signal_contribution(factors, VolatilityRegime.HIGH_VOL)
    assert score == 0.0
    assert mult == 1.10
