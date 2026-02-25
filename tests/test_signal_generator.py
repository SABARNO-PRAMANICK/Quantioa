"""
Tests for SignalGenerator with sentiment integration.
"""

from quantioa.engine.signal_generator import SignalGenerator
from quantioa.models.enums import TradeSignal, VolatilityRegime


def test_signal_generator_with_positive_sentiment():
    """Verify sentiment score adds to the combined signal."""
    sg = SignalGenerator()
    
    # Neutral/weak technicals
    ind = {
        "rsi": 50, "macd_hist": 0, "macd_line": 0, "macd_signal": 0,
        "ema_9": 100, "ema_21": 100, "ema_55": 100,
        "sma_20": 100, "sma_50": 100, "close": 100,
    }
    
    # Sentiment is highly positive
    sentiment_result = {
        "weighted_score": 1.0,           # Max positive sentiment
        "influence_multiplier": 1.10,    # HIGH_VOL amplification
        "stale": False,                  # Fresh data
    }
    
    output = sg.generate(indicators=ind, sentiment_result=sentiment_result)
    
    # W_SENTIMENT = 0.15. Score = 1.0 * 1.10 = 1.10. 
    # Contribution = 0.15 * 1.10 = 0.165
    # Technicals are close to 0, so combined should be ~0.165 (> 0.15 threshold for BUY)
    assert output.signal == TradeSignal.BUY
    assert output.sentiment_influence == 1.10
    assert output.sentiment_score == 1.0
    assert output.sentiment_stale is False


def test_signal_generator_with_stale_sentiment():
    """Verify stale sentiment is halved."""
    sg = SignalGenerator()
    
    ind = {
        "rsi": 50, "macd_hist": 0, "macd_line": 0, "macd_signal": 0,
        "ema_9": 100, "ema_21": 100, "ema_55": 100,
        "sma_20": 100, "sma_50": 100, "close": 100,
    }
    
    sentiment_result = {
        "weighted_score": 1.0,
        "influence_multiplier": 1.0,
        "stale": True,
    }
    
    output = sg.generate(indicators=ind, sentiment_result=sentiment_result)
    
    # W_SENTIMENT = 0.15. Base Score = 1.0 * 1.0 = 1.0. 
    # Stale penalizes score by 50% -> 0.5. Contribution = 0.15 * 0.5 = 0.075
    # Combined = 0.075 (< 0.15 threshold for BUY)
    assert output.signal == TradeSignal.HOLD
    assert getattr(output, "sentiment_stale", False) is True
