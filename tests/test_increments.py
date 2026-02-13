"""
Unit tests for trading increments 1–4.
"""

import pytest

from quantioa.increments.inc1_microstructure import OrderFlowAnalyzer
from quantioa.increments.inc2_volatility import VolatilityRegimeDetector
from quantioa.increments.inc4_kelly import KellyCriterionSizer
from quantioa.models.enums import TradeSignal, TradeSide, VolatilityRegime
from quantioa.models.types import OrderBookLevel, OrderBookSnapshot, TradeResult


class TestOrderFlowAnalyzer:
    def _make_book(self, bid_qty: int, ask_qty: int) -> OrderBookSnapshot:
        return OrderBookSnapshot(
            symbol="TEST",
            bids=[OrderBookLevel(price=100, quantity=bid_qty)],
            asks=[OrderBookLevel(price=101, quantity=ask_qty)],
            timestamp=0.0,
        )

    def test_accumulation_signals_buy(self):
        ofi = OrderFlowAnalyzer()
        result = ofi.analyze(self._make_book(1000, 200))
        assert result.ofi > 0
        assert result.signal == TradeSignal.BUY

    def test_distribution_signals_sell(self):
        ofi = OrderFlowAnalyzer()
        result = ofi.analyze(self._make_book(200, 1000))
        assert result.ofi < 0
        assert result.signal == TradeSignal.SELL

    def test_balanced_signals_hold(self):
        ofi = OrderFlowAnalyzer()
        result = ofi.analyze(self._make_book(500, 500))
        assert result.ofi == pytest.approx(0.0)
        assert result.signal == TradeSignal.HOLD


class TestVolatilityRegimeDetector:
    def test_normal_regime(self):
        detector = VolatilityRegimeDetector()
        result = detector.detect(atr=100, close_price=2200)
        # 100/2200 ≈ 4.5% → NORMAL
        assert result.regime == VolatilityRegime.NORMAL

    def test_high_vol(self):
        detector = VolatilityRegimeDetector()
        result = detector.detect(atr=200, close_price=2200)
        # 200/2200 ≈ 9.1% → HIGH_VOL
        assert result.regime == VolatilityRegime.HIGH_VOL

    def test_low_vol(self):
        detector = VolatilityRegimeDetector()
        result = detector.detect(atr=30, close_price=2200)
        # 30/2200 ≈ 1.4% → LOW_VOL
        assert result.regime == VolatilityRegime.LOW_VOL

    def test_position_multiplier_decreases_in_high_vol(self):
        detector = VolatilityRegimeDetector()
        normal = detector.detect(atr=100, close_price=2200)
        high = detector.detect(atr=200, close_price=2200)
        assert high.position_size_multiplier < normal.position_size_multiplier


class TestKellyCriterionSizer:
    def _make_trade(self, pnl: float) -> TradeResult:
        entry = 100.0
        exit_price = entry + pnl
        return TradeResult(
            id="T-1",
            symbol="TEST",
            side=TradeSide.LONG,
            quantity=1,
            entry_price=entry,
            exit_price=exit_price,
            entry_time=0.0,
            exit_time=1.0,
        )

    def test_conservative_without_history(self):
        kelly = KellyCriterionSizer()
        result = kelly.calculate(capital=100_000, entry_price=100, stop_loss_price=95)
        assert result.is_active is False
        assert result.fractional_kelly == 0.01  # conservative default

    def test_kelly_with_winning_history(self):
        kelly = KellyCriterionSizer(min_trades=5)
        for _ in range(8):
            kelly.add_trade(self._make_trade(pnl=10.0))  # wins
        for _ in range(2):
            kelly.add_trade(self._make_trade(pnl=-5.0))  # losses

        result = kelly.calculate(capital=100_000, entry_price=100, stop_loss_price=95)
        assert result.is_active is True
        assert result.full_kelly > 0  # positive edge

    def test_no_edge_zero_kelly(self):
        kelly = KellyCriterionSizer(min_trades=5)
        for _ in range(5):
            kelly.add_trade(self._make_trade(pnl=-10.0))  # all losses
        for _ in range(5):
            kelly.add_trade(self._make_trade(pnl=2.0))  # small wins

        result = kelly.calculate(capital=100_000, entry_price=100, stop_loss_price=95)
        # avg_loss >> avg_win with low win rate → no edge
        assert result.full_kelly == 0.0 or result.full_kelly < 0.05
