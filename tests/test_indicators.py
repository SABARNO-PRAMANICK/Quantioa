"""
Unit tests for the streaming indicator suite.
"""

import pytest

from quantioa.indicators.streaming import (
    StreamingATR,
    StreamingEMA,
    StreamingMACD,
    StreamingOBV,
    StreamingRSI,
    StreamingSMA,
    StreamingVWAP,
)
from quantioa.indicators.suite import StreamingIndicatorSuite
from quantioa.models.types import Tick


class TestStreamingSMA:
    def test_window_average(self):
        sma = StreamingSMA(period=3)
        assert sma.update(10.0) == pytest.approx(10.0)
        assert sma.update(20.0) == pytest.approx(15.0)
        assert sma.update(30.0) == pytest.approx(20.0)
        assert sma.update(40.0) == pytest.approx(30.0)  # (20+30+40)/3

    def test_constant_input(self):
        sma = StreamingSMA(period=5)
        for _ in range(10):
            result = sma.update(100.0)
        assert result == pytest.approx(100.0)


class TestStreamingEMA:
    def test_converges_to_constant(self):
        ema = StreamingEMA(period=10)
        for _ in range(50):
            result = ema.update(50.0)
        assert result == pytest.approx(50.0, abs=0.01)

    def test_reacts_to_change(self):
        ema = StreamingEMA(period=5)
        for _ in range(20):
            ema.update(100.0)
        # Price jumps — EMA should move toward new price
        result = ema.update(200.0)
        assert 100.0 < result < 200.0


class TestStreamingRSI:
    def test_all_gains_near_100(self):
        rsi = StreamingRSI(period=14)
        for i in range(50):
            result = rsi.update(100.0 + i)  # strictly rising
        assert result > 70  # should be strongly overbought

    def test_all_losses_near_0(self):
        rsi = StreamingRSI(period=14)
        for i in range(50):
            result = rsi.update(100.0 - i * 0.5)  # falling
        assert result < 30  # should be oversold

    def test_range_bounds(self):
        rsi = StreamingRSI(period=14)
        for i in range(100):
            result = rsi.update(100 + (i % 5))
        assert 0 <= result <= 100


class TestStreamingMACD:
    def test_outputs_three_values(self):
        macd = StreamingMACD()
        for i in range(30):
            result = macd.update(100.0 + i * 0.1)
        assert len(result) == 3  # (macd_line, signal, histogram)

    def test_histogram_is_difference(self):
        macd = StreamingMACD()
        for i in range(50):
            line, signal, hist = macd.update(100.0 + i)
        assert hist == pytest.approx(line - signal, abs=0.001)


class TestStreamingATR:
    def test_atr_positive(self):
        atr = StreamingATR(period=14)
        for i in range(30):
            result = atr.update(high=105 + i, low=95 + i, close=100 + i)
        assert result > 0

    def test_atr_zero_range(self):
        """When H=L=C, ATR should go toward 0."""
        atr = StreamingATR(period=5)
        for _ in range(50):
            result = atr.update(high=100, low=100, close=100)
        assert result == pytest.approx(0.0, abs=0.1)


class TestStreamingSuite:
    def _make_tick(self, i: int, base: float = 22000.0) -> Tick:
        return Tick(
            timestamp=float(i),
            symbol="TEST",
            open=base + i,
            high=base + i + 2,
            low=base + i - 2,
            close=base + i + 0.5,
            volume=10000,
        )

    def test_update_returns_snapshot(self):
        suite = StreamingIndicatorSuite()
        tick = self._make_tick(0)
        snap = suite.update(tick)
        # Should have all indicator fields
        assert hasattr(snap, "rsi")
        assert hasattr(snap, "macd_line")
        assert hasattr(snap, "atr")
        assert hasattr(snap, "vwap")
        assert hasattr(snap, "sma_20")

    def test_50_ticks_no_crash(self):
        suite = StreamingIndicatorSuite()
        for i in range(50):
            snap = suite.update(self._make_tick(i))
        assert snap.rsi > 0
        assert snap.atr > 0
