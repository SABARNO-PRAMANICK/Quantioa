"""
Increment 8 — Execution Optimization.

Provides:
- SlippagePredictor:  Estimates slippage before order placement.
- TWAPStrategy:       Time-Weighted Average Price child-order scheduler.
- VWAPStrategy:       Volume-Weighted Average Price child-order scheduler.
- ExecutionManager:   Decides the optimal execution strategy and coordinates
                      parent → child order lifecycle.

All classes are stateless per invocation so they can be shared across
multiple symbols safely.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from quantioa.models.enums import ExecutionStrategy, OrderStatus, TradeSide
from quantioa.models.types import (
    ChildOrder,
    ExecutionPlan,
    Order,
    OrderBookSnapshot,
    ParentOrder,
)

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

_DEFAULT_SLIPPAGE_MULTIPLIER = 0.5  # basis-point multiplier
_TWAP_MIN_SLICES = 2
_TWAP_MAX_SLICES = 20
_VWAP_MIN_SLICES = 3
_VWAP_MAX_SLICES = 30

# Thresholds for automatic strategy selection
_LARGE_ORDER_LIQUIDITY_RATIO = 0.15  # order > 15% of visible liquidity
_URGENT_SLIPPAGE_THRESHOLD_BPS = 5.0  # accept up to 5 bps for market orders
_HIGH_SLIPPAGE_THRESHOLD_BPS = 20.0  # above this, always use algo execution


# ── Slippage Predictor ─────────────────────────────────────────────────────────


@dataclass(slots=True)
class SlippagePrediction:
    """Result of a slippage prediction."""

    predicted_bps: float  # basis points
    predicted_cost: float  # absolute ₹ cost
    liquidity_ratio: float  # order_size / visible_liquidity
    volatility_multiplier: float
    confidence: float  # 0-1, how confident we are in the prediction


class SlippagePredictor:
    """Predicts execution slippage from order book depth and volatility.

    Formula
    -------
    predicted_slippage = (order_size / available_liquidity) * vol_multiplier

    The ``vol_multiplier`` scales slippage up during high-volatility
    regimes (wider spreads, thinner books).
    """

    def predict(
        self,
        order_quantity: int,
        order_book: OrderBookSnapshot,
        *,
        side: TradeSide,
        atr_pct: float = 1.0,
    ) -> SlippagePrediction:
        """Predict slippage for a hypothetical order.

        Args:
            order_quantity: Number of shares/lots to trade.
            order_book: Current order book depth snapshot.
            side: BUY (consume asks) or SELL (consume bids).
            atr_pct: ATR as a percentage of price (volatility proxy).
        """
        levels = order_book.asks if side == TradeSide.LONG else order_book.bids

        total_liquidity = sum(lvl.quantity for lvl in levels) if levels else 1
        liquidity_ratio = order_quantity / max(total_liquidity, 1)

        # Volatility multiplier: higher ATR → wider effective spreads
        vol_mult = max(1.0, atr_pct / 1.0)  # normalised around 1% ATR

        raw_bps = liquidity_ratio * vol_mult * _DEFAULT_SLIPPAGE_MULTIPLIER * 100
        # Walk the book to get a more precise cost estimate
        cost = self._walk_book(order_quantity, levels)

        confidence = min(1.0, len(levels) / 5)  # more depth → more confident

        return SlippagePrediction(
            predicted_bps=round(raw_bps, 2),
            predicted_cost=round(cost, 2),
            liquidity_ratio=round(liquidity_ratio, 4),
            volatility_multiplier=round(vol_mult, 2),
            confidence=round(confidence, 2),
        )

    @staticmethod
    def _walk_book(quantity: int, levels: list) -> float:
        """Simulate walking the order book to estimate fill cost."""
        remaining = quantity
        total_cost = 0.0
        mid_price = levels[0].price if levels else 0.0

        for level in levels:
            fill = min(remaining, level.quantity)
            total_cost += fill * abs(level.price - mid_price)
            remaining -= fill
            if remaining <= 0:
                break

        return total_cost


# ── Execution Algorithm Interface ──────────────────────────────────────────────


class ExecutionAlgo(ABC):
    """Base class for algorithmic order execution strategies."""

    @abstractmethod
    def generate_schedule(
        self,
        symbol: str,
        side: TradeSide,
        total_quantity: int,
        duration_seconds: float,
        current_price: float,
    ) -> ParentOrder:
        """Generate a parent order with scheduled child slices."""
        ...


# ── TWAP Strategy ──────────────────────────────────────────────────────────────


class TWAPStrategy(ExecutionAlgo):
    """Time-Weighted Average Price — splits an order into equal time slices.

    Each child order is placed at uniform intervals over the given
    ``duration_seconds``. All slices have equal quantity (remainder
    added to the last slice).
    """

    def __init__(self, num_slices: int | None = None) -> None:
        self._num_slices = num_slices

    def generate_schedule(
        self,
        symbol: str,
        side: TradeSide,
        total_quantity: int,
        duration_seconds: float,
        current_price: float,
    ) -> ParentOrder:
        n = self._num_slices or self._auto_slices(total_quantity)
        n = max(_TWAP_MIN_SLICES, min(n, _TWAP_MAX_SLICES))
        # Never create more slices than quantity (prevents zero-qty children)
        n = min(n, total_quantity)

        base_qty = total_quantity // n
        remainder = total_quantity % n
        interval = duration_seconds / n
        now = time.time()

        children: list[ChildOrder] = []
        for i in range(n):
            qty = base_qty + (1 if i < remainder else 0)
            children.append(
                ChildOrder(
                    order_id=f"TW-{uuid.uuid4().hex[:8]}",
                    sequence=i + 1,
                    quantity=qty,
                    target_price=current_price,
                    scheduled_time=now + interval * i,
                )
            )

        parent = ParentOrder(
            parent_id=f"P-{uuid.uuid4().hex[:8]}",
            symbol=symbol,
            side=side,
            total_quantity=total_quantity,
            strategy=ExecutionStrategy.TWAP,
            children=children,
            created_at=now,
        )

        logger.info(
            "TWAP schedule: %d slices × ~%d qty over %.0fs for %s",
            n, base_qty, duration_seconds, symbol,
        )
        return parent

    @staticmethod
    def _auto_slices(qty: int) -> int:
        """Heuristic: more quantity → more slices."""
        if qty <= 50:
            return 2
        if qty <= 200:
            return 5
        if qty <= 1000:
            return 10
        return 15


# ── VWAP Strategy ──────────────────────────────────────────────────────────────


class VWAPStrategy(ExecutionAlgo):
    """Volume-Weighted Average Price — weights child orders by a volume profile.

    If a historical intraday volume profile is provided, slices are
    weighted so that larger orders execute during high-volume periods
    (less market impact).  Falls back to a simple U-shaped curve
    (open/close heavier) when no profile is available.
    """

    def __init__(
        self,
        volume_profile: list[float] | None = None,
        num_slices: int | None = None,
    ) -> None:
        self._profile = volume_profile
        self._num_slices = num_slices

    def generate_schedule(
        self,
        symbol: str,
        side: TradeSide,
        total_quantity: int,
        duration_seconds: float,
        current_price: float,
    ) -> ParentOrder:
        n = self._num_slices or self._auto_slices(total_quantity)
        n = max(_VWAP_MIN_SLICES, min(n, _VWAP_MAX_SLICES))
        # Never create more slices than quantity (prevents zero-qty children)
        n = min(n, total_quantity)

        weights = self._get_weights(n)
        interval = duration_seconds / n
        now = time.time()

        children: list[ChildOrder] = []
        allocated = 0
        for i in range(n):
            if i == n - 1:
                # Last slice gets whatever remains to avoid rounding drift
                qty = total_quantity - allocated
            else:
                qty = max(1, round(total_quantity * weights[i]))
                allocated += qty

            children.append(
                ChildOrder(
                    order_id=f"VW-{uuid.uuid4().hex[:8]}",
                    sequence=i + 1,
                    quantity=qty,
                    target_price=current_price,
                    scheduled_time=now + interval * i,
                )
            )

        # Filter out any zero-qty children from rounding edge cases
        children = [c for c in children if c.quantity > 0]

        parent = ParentOrder(
            parent_id=f"P-{uuid.uuid4().hex[:8]}",
            symbol=symbol,
            side=side,
            total_quantity=total_quantity,
            strategy=ExecutionStrategy.VWAP,
            children=children,
            created_at=now,
        )

        logger.info(
            "VWAP schedule: %d slices (weighted) over %.0fs for %s",
            n, duration_seconds, symbol,
        )
        return parent

    def _get_weights(self, n: int) -> list[float]:
        """Return normalised weights for each slice."""
        if self._profile and len(self._profile) == n:
            total = sum(self._profile)
            return [w / total for w in self._profile] if total > 0 else [1 / n] * n

        # Default U-shaped profile (heavier at open + close)
        raw = []
        for i in range(n):
            x = i / max(n - 1, 1)  # 0..1
            # U-shape: high at edges, lower in middle
            w = 1.0 + 1.5 * (2 * x - 1) ** 2
            raw.append(w)

        total = sum(raw)
        return [w / total for w in raw]

    @staticmethod
    def _auto_slices(qty: int) -> int:
        if qty <= 100:
            return 3
        if qty <= 500:
            return 8
        if qty <= 2000:
            return 15
        return 20


# ── Execution Manager ──────────────────────────────────────────────────────────


class ExecutionManager:
    """Decides the optimal execution strategy and creates execution plans.

    Decision matrix
    ---------------
    * Predicted slippage <= 5 bps  → MARKET order (fast, acceptable cost)
    * Predicted slippage 5–20 bps  → LIMIT order (passive, wait for fill)
    * Predicted slippage > 20 bps  → TWAP/VWAP (algo execution, slice it)
    * Emergency exits (stop-loss)  → Always MARKET (speed > cost)

    Usage::

        mgr = ExecutionManager()
        plan = mgr.evaluate(order_qty=200, book=snapshot, side=LONG, atr_pct=2.5)
        if plan.strategy == ExecutionStrategy.VWAP:
            parent = mgr.create_vwap_schedule(...)
    """

    def __init__(
        self,
        slippage_predictor: SlippagePredictor | None = None,
        twap: TWAPStrategy | None = None,
        vwap: VWAPStrategy | None = None,
        *,
        urgent_threshold_bps: float = _URGENT_SLIPPAGE_THRESHOLD_BPS,
        high_threshold_bps: float = _HIGH_SLIPPAGE_THRESHOLD_BPS,
        default_algo_duration_seconds: float = 600.0,  # 10 minutes
    ) -> None:
        self.predictor = slippage_predictor or SlippagePredictor()
        self.twap = twap or TWAPStrategy()
        self.vwap = vwap or VWAPStrategy()
        self._urgent_bps = urgent_threshold_bps
        self._high_bps = high_threshold_bps
        self._default_duration = default_algo_duration_seconds

    def evaluate(
        self,
        order_quantity: int,
        order_book: OrderBookSnapshot,
        side: TradeSide,
        atr_pct: float = 1.0,
        *,
        is_emergency: bool = False,
    ) -> ExecutionPlan:
        """Evaluate the best execution strategy for this order.

        Args:
            order_quantity: Shares/lots to execute.
            order_book: Current market depth.
            side: BUY or SELL.
            atr_pct: ATR / close (volatility estimate).
            is_emergency: True for stop-loss exits — forces MARKET.
        """
        if is_emergency:
            return ExecutionPlan(
                strategy=ExecutionStrategy.MARKET,
                predicted_slippage_pct=0.0,
                predicted_cost=0.0,
                reasoning="Emergency exit — market order for speed.",
            )

        pred = self.predictor.predict(
            order_quantity, order_book, side=side, atr_pct=atr_pct,
        )

        if pred.predicted_bps <= self._urgent_bps:
            strategy = ExecutionStrategy.MARKET
            reasoning = (
                f"Low predicted slippage ({pred.predicted_bps:.1f} bps). "
                "Market order is optimal."
            )
        elif pred.predicted_bps <= self._high_bps:
            strategy = ExecutionStrategy.LIMIT
            reasoning = (
                f"Moderate slippage ({pred.predicted_bps:.1f} bps). "
                "Using limit order for passive fill."
            )
        else:
            # Prefer VWAP for large orders, TWAP for moderate
            if pred.liquidity_ratio > 0.3:
                strategy = ExecutionStrategy.VWAP
                reasoning = (
                    f"High slippage ({pred.predicted_bps:.1f} bps), "
                    f"liquidity ratio {pred.liquidity_ratio:.1%}. "
                    "Using VWAP to minimise market impact."
                )
            else:
                strategy = ExecutionStrategy.TWAP
                reasoning = (
                    f"High slippage ({pred.predicted_bps:.1f} bps). "
                    "Using TWAP to distribute execution over time."
                )

        logger.info(
            "Execution evaluation: %s | slippage=%.1f bps | liq_ratio=%.2f | %s",
            strategy.value, pred.predicted_bps, pred.liquidity_ratio, reasoning,
        )

        return ExecutionPlan(
            strategy=strategy,
            predicted_slippage_pct=round(pred.predicted_bps / 100, 4),
            predicted_cost=pred.predicted_cost,
            reasoning=reasoning,
        )

    def create_schedule(
        self,
        strategy: ExecutionStrategy,
        symbol: str,
        side: TradeSide,
        total_quantity: int,
        current_price: float,
        duration_seconds: float | None = None,
    ) -> ParentOrder:
        """Create a parent order schedule for the chosen algo strategy.

        For MARKET / LIMIT strategies, returns a single-child parent.
        """
        duration = duration_seconds or self._default_duration

        if strategy == ExecutionStrategy.TWAP:
            return self.twap.generate_schedule(
                symbol, side, total_quantity, duration, current_price,
            )
        elif strategy == ExecutionStrategy.VWAP:
            return self.vwap.generate_schedule(
                symbol, side, total_quantity, duration, current_price,
            )
        else:
            # MARKET and LIMIT → single child (immediate execution)
            now = time.time()
            child = ChildOrder(
                order_id=f"MK-{uuid.uuid4().hex[:8]}",
                sequence=1,
                quantity=total_quantity,
                target_price=current_price,
                scheduled_time=now,
            )
            return ParentOrder(
                parent_id=f"P-{uuid.uuid4().hex[:8]}",
                symbol=symbol,
                side=side,
                total_quantity=total_quantity,
                strategy=strategy,
                children=[child],
                created_at=now,
            )

    @staticmethod
    def record_fill(
        child: ChildOrder,
        filled_price: float,
        filled_quantity: int,
    ) -> None:
        """Record a fill against a child order and compute slippage."""
        child.filled_price = filled_price
        child.filled_quantity = filled_quantity
        child.executed_time = time.time()
        child.status = OrderStatus.FILLED

        if child.target_price > 0:
            child.slippage_bps = (
                abs(filled_price - child.target_price) / child.target_price * 10_000
            )

    @staticmethod
    def update_parent(parent: ParentOrder) -> None:
        """Recompute parent aggregate metrics from children."""
        filled_children = [c for c in parent.children if c.filled_quantity > 0]
        parent.filled_quantity = sum(c.filled_quantity for c in filled_children)

        if parent.filled_quantity > 0:
            parent.average_fill_price = (
                sum(c.filled_price * c.filled_quantity for c in filled_children)
                / parent.filled_quantity
            )

        if parent.filled_quantity >= parent.total_quantity:
            parent.is_complete = True
            parent.completed_at = time.time()
