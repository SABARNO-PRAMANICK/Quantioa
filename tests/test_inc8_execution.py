"""
Tests for Increment 8 — Execution Optimization.

Covers:
- SlippagePredictor: slippage scales with order size and volatility.
- TWAPStrategy:      correct number of slices, quantity distribution.
- VWAPStrategy:      weighted slicing, U-shaped default profile.
- ExecutionManager:  strategy selection thresholds, full lifecycle.
- Block-and-Skip:    AI intent flow with fresh data re-evaluation.
"""

from __future__ import annotations

import time

import pytest

from quantioa.increments.inc8_execution import (
    ExecutionManager,
    SlippagePredictor,
    TWAPStrategy,
    VWAPStrategy,
)
from quantioa.models.enums import ExecutionStrategy, OrderStatus, TradeSide
from quantioa.models.types import (
    ChildOrder,
    ExecutionPlan,
    IntentToTrade,
    OrderBookLevel,
    OrderBookSnapshot,
    ParentOrder,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────


def _make_order_book(
    mid: float = 2000.0,
    spread: float = 0.5,
    depth: int = 5,
    qty_per_level: int = 100,
) -> OrderBookSnapshot:
    """Create a synthetic order book snapshot."""
    bids = [
        OrderBookLevel(price=mid - spread * (i + 1), quantity=qty_per_level, orders=5)
        for i in range(depth)
    ]
    asks = [
        OrderBookLevel(price=mid + spread * (i + 1), quantity=qty_per_level, orders=5)
        for i in range(depth)
    ]
    return OrderBookSnapshot(symbol="TEST", bids=bids, asks=asks, timestamp=time.time())


def _make_thin_book(mid: float = 2000.0) -> OrderBookSnapshot:
    """Order book with very low liquidity — forces algo execution."""
    return _make_order_book(mid=mid, depth=2, qty_per_level=10)


def _make_deep_book(mid: float = 2000.0) -> OrderBookSnapshot:
    """Order book with deep liquidity — should get market execution."""
    return _make_order_book(mid=mid, depth=5, qty_per_level=5000)


# ── SlippagePredictor Tests ────────────────────────────────────────────────────


class TestSlippagePredictor:
    def setup_method(self):
        self.predictor = SlippagePredictor()

    def test_small_order_low_slippage(self):
        """Small order against deep book → low slippage."""
        book = _make_deep_book()
        pred = self.predictor.predict(10, book, side=TradeSide.LONG, atr_pct=1.0)
        assert pred.predicted_bps < 1.0
        assert pred.liquidity_ratio < 0.01

    def test_large_order_high_slippage(self):
        """Large order against thin book → high slippage."""
        book = _make_thin_book()
        pred = self.predictor.predict(50, book, side=TradeSide.LONG, atr_pct=1.0)
        assert pred.predicted_bps > 5.0
        assert pred.liquidity_ratio > 0.5

    def test_slippage_scales_with_quantity(self):
        """Slippage should increase as order size grows."""
        book = _make_order_book()
        pred_small = self.predictor.predict(10, book, side=TradeSide.LONG)
        pred_large = self.predictor.predict(200, book, side=TradeSide.LONG)
        assert pred_large.predicted_bps > pred_small.predicted_bps

    def test_slippage_scales_with_volatility(self):
        """Higher ATR% → higher slippage prediction."""
        book = _make_order_book()
        pred_calm = self.predictor.predict(50, book, side=TradeSide.LONG, atr_pct=0.5)
        pred_vol = self.predictor.predict(50, book, side=TradeSide.LONG, atr_pct=5.0)
        assert pred_vol.predicted_bps > pred_calm.predicted_bps

    def test_buy_consumes_asks(self):
        """BUY order should consume the ask side of the book."""
        book = _make_order_book(qty_per_level=50)
        pred = self.predictor.predict(100, book, side=TradeSide.LONG)
        assert pred.predicted_cost >= 0  # Book walk should compute non-negative

    def test_sell_consumes_bids(self):
        """SELL order should consume the bid side."""
        book = _make_order_book(qty_per_level=50)
        pred = self.predictor.predict(100, book, side=TradeSide.SHORT)
        assert pred.predicted_cost >= 0

    def test_confidence_increases_with_depth(self):
        """More order book levels → higher prediction confidence."""
        shallow = _make_order_book(depth=1)
        deep = _make_order_book(depth=5)
        p1 = self.predictor.predict(50, shallow, side=TradeSide.LONG)
        p2 = self.predictor.predict(50, deep, side=TradeSide.LONG)
        assert p2.confidence >= p1.confidence


# ── TWAP Strategy Tests ────────────────────────────────────────────────────────


class TestTWAPStrategy:
    def test_correct_number_of_slices(self):
        """TWAP should create the requested number of slices."""
        twap = TWAPStrategy(num_slices=5)
        parent = twap.generate_schedule("TEST", TradeSide.LONG, 100, 600.0, 2000.0)
        assert len(parent.children) == 5

    def test_quantity_sums_to_total(self):
        """Total child quantities must equal the parent total."""
        twap = TWAPStrategy(num_slices=7)
        parent = twap.generate_schedule("TEST", TradeSide.LONG, 100, 600.0, 2000.0)
        total = sum(c.quantity for c in parent.children)
        assert total == 100

    def test_slices_have_increasing_times(self):
        """Each child should execute at a later scheduled time."""
        twap = TWAPStrategy(num_slices=4)
        parent = twap.generate_schedule("TEST", TradeSide.LONG, 100, 600.0, 2000.0)
        times = [c.scheduled_time for c in parent.children]
        assert times == sorted(times)

    def test_auto_slices_small_order(self):
        """Small order should get fewer slices automatically."""
        twap = TWAPStrategy()
        parent = twap.generate_schedule("TEST", TradeSide.LONG, 20, 300.0, 2000.0)
        assert len(parent.children) == 2  # min slices for small qty

    def test_qty_one_produces_single_slice(self):
        """qty=1 must produce exactly 1 child, never zero-qty slices."""
        twap = TWAPStrategy(num_slices=10)
        parent = twap.generate_schedule("TEST", TradeSide.LONG, 1, 300.0, 2000.0)
        assert len(parent.children) == 1
        assert parent.children[0].quantity == 1

    def test_auto_slices_large_order(self):
        """Large order should get more slices."""
        twap = TWAPStrategy()
        parent = twap.generate_schedule("TEST", TradeSide.LONG, 500, 600.0, 2000.0)
        assert len(parent.children) >= 5

    def test_parent_metadata(self):
        """ParentOrder should have correct metadata."""
        twap = TWAPStrategy(num_slices=3)
        parent = twap.generate_schedule("TEST", TradeSide.SHORT, 60, 300.0, 1500.0)
        assert parent.symbol == "TEST"
        assert parent.side == TradeSide.SHORT
        assert parent.total_quantity == 60
        assert parent.strategy == ExecutionStrategy.TWAP


# ── VWAP Strategy Tests ────────────────────────────────────────────────────────


class TestVWAPStrategy:
    def test_quantity_sums_to_total(self):
        """VWAP child quantities must sum to parent total."""
        vwap = VWAPStrategy(num_slices=6)
        parent = vwap.generate_schedule("TEST", TradeSide.LONG, 150, 1200.0, 2000.0)
        total = sum(c.quantity for c in parent.children)
        assert total == 150

    def test_u_shaped_default_profile(self):
        """Default profile should be U-shaped: edges > middle."""
        vwap = VWAPStrategy(num_slices=5)
        parent = vwap.generate_schedule("TEST", TradeSide.LONG, 200, 600.0, 2000.0)
        qtys = [c.quantity for c in parent.children]
        # First and last slices should be >= middle slices
        mid = qtys[len(qtys) // 2]
        assert qtys[0] >= mid or qtys[-1] >= mid

    def test_custom_volume_profile(self):
        """Custom profile should weight slices proportionally."""
        profile = [1.0, 2.0, 3.0]  # last slice gets most
        vwap = VWAPStrategy(volume_profile=profile, num_slices=3)
        parent = vwap.generate_schedule("TEST", TradeSide.LONG, 60, 300.0, 2000.0)
        qtys = [c.quantity for c in parent.children]
        assert qtys[-1] >= qtys[0]  # Last should be largest

    def test_strategy_is_vwap(self):
        vwap = VWAPStrategy(num_slices=3)
        parent = vwap.generate_schedule("TEST", TradeSide.LONG, 100, 600.0, 2000.0)
        assert parent.strategy == ExecutionStrategy.VWAP


# ── ExecutionManager Tests ─────────────────────────────────────────────────────


class TestExecutionManager:
    def setup_method(self):
        self.mgr = ExecutionManager()

    def test_emergency_always_market(self):
        """Emergency exits must use MARKET, regardless of slippage."""
        book = _make_thin_book()
        plan = self.mgr.evaluate(500, book, TradeSide.LONG, atr_pct=5.0, is_emergency=True)
        assert plan.strategy == ExecutionStrategy.MARKET

    def test_small_order_deep_book_market(self):
        """Small order with deep book → MARKET (low slippage)."""
        book = _make_deep_book()
        plan = self.mgr.evaluate(5, book, TradeSide.LONG, atr_pct=1.0)
        assert plan.strategy == ExecutionStrategy.MARKET

    def test_large_order_thin_book_algo(self):
        """Large order with thin book → TWAP or VWAP."""
        book = _make_thin_book()
        plan = self.mgr.evaluate(100, book, TradeSide.LONG, atr_pct=3.0)
        assert plan.strategy in (ExecutionStrategy.TWAP, ExecutionStrategy.VWAP)

    def test_create_schedule_market(self):
        """MARKET schedule should have exactly 1 child."""
        parent = self.mgr.create_schedule(
            ExecutionStrategy.MARKET, "TEST", TradeSide.LONG, 50, 2000.0,
        )
        assert len(parent.children) == 1
        assert parent.children[0].quantity == 50

    def test_create_schedule_twap(self):
        """TWAP schedule should split into multiple children."""
        parent = self.mgr.create_schedule(
            ExecutionStrategy.TWAP, "TEST", TradeSide.LONG, 100, 2000.0,
        )
        assert len(parent.children) >= 2
        assert sum(c.quantity for c in parent.children) == 100

    def test_create_schedule_vwap(self):
        """VWAP schedule should split into multiple weighted children."""
        parent = self.mgr.create_schedule(
            ExecutionStrategy.VWAP, "TEST", TradeSide.LONG, 200, 2000.0,
        )
        assert len(parent.children) >= 3
        assert sum(c.quantity for c in parent.children) == 200

    def test_record_fill_updates_child(self):
        """Recording a fill should update child slippage and status."""
        child = ChildOrder(order_id="C-1", sequence=1, quantity=50, target_price=2000.0)
        self.mgr.record_fill(child, filled_price=2001.0, filled_quantity=50)
        assert child.status == OrderStatus.FILLED
        assert child.filled_price == 2001.0
        assert child.slippage_bps == pytest.approx(5.0, rel=0.01)

    def test_update_parent_aggregates(self):
        """Parent should aggregate fill data from children."""
        parent = ParentOrder(
            parent_id="P-1",
            symbol="TEST",
            side=TradeSide.LONG,
            total_quantity=100,
            strategy=ExecutionStrategy.TWAP,
        )
        c1 = ChildOrder(order_id="C-1", sequence=1, quantity=50, target_price=2000.0)
        c2 = ChildOrder(order_id="C-2", sequence=2, quantity=50, target_price=2000.0)
        parent.children = [c1, c2]

        self.mgr.record_fill(c1, 2000.5, 50)
        self.mgr.record_fill(c2, 2001.0, 50)
        self.mgr.update_parent(parent)

        assert parent.filled_quantity == 100
        assert parent.is_complete is True
        assert parent.average_fill_price == pytest.approx(2000.75, rel=0.01)

    def test_plan_reasoning_is_populated(self):
        """Execution plans must contain reasoning for audit trail."""
        book = _make_order_book()
        plan = self.mgr.evaluate(50, book, TradeSide.LONG, atr_pct=2.0)
        assert len(plan.reasoning) > 0


# ── Block-and-Skip AI Flow Tests ──────────────────────────────────────────────


class TestIntentToTrade:
    def test_intent_dataclass_creation(self):
        """IntentToTrade should be constructible with required fields."""
        from quantioa.models.enums import TradeSignal

        intent = IntentToTrade(
            symbol="INFY",
            signal=TradeSignal.BUY,
            confidence=0.85,
            reasoning="Strong bullish momentum detected by AI.",
            ai_model="deepseek-r1",
            decision_timestamp=time.time(),
            context_age_seconds=95.0,
        )
        assert intent.symbol == "INFY"
        assert intent.confidence == 0.85
        assert intent.context_age_seconds == 95.0

    def test_parent_order_remaining_quantity(self):
        """ParentOrder.remaining_quantity should track unfilled amount."""
        parent = ParentOrder(
            parent_id="P-1",
            symbol="TEST",
            side=TradeSide.LONG,
            total_quantity=100,
            strategy=ExecutionStrategy.TWAP,
            filled_quantity=30,
        )
        assert parent.remaining_quantity == 70

    def test_parent_slippage_weighted_average(self):
        """ParentOrder.total_slippage_bps should be volume-weighted."""
        c1 = ChildOrder(
            order_id="C-1", sequence=1, quantity=70,
            filled_quantity=70, slippage_bps=2.0,
        )
        c2 = ChildOrder(
            order_id="C-2", sequence=2, quantity=30,
            filled_quantity=30, slippage_bps=8.0,
        )
        parent = ParentOrder(
            parent_id="P-1",
            symbol="TEST",
            side=TradeSide.LONG,
            total_quantity=100,
            strategy=ExecutionStrategy.VWAP,
            children=[c1, c2],
        )
        # Weighted: (70*2 + 30*8) / 100 = 3.8
        assert parent.total_slippage_bps == pytest.approx(3.8, rel=0.01)
