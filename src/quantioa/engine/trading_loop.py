"""
Trading Loop — the main orchestrator.

Each cycle:
1. Receive tick data
2. Update indicators
3. Run increments (OFI, volatility, Kelly)
4. Generate signal
5. Check risk
6. Confirm trade
7. Evaluate execution strategy (Phase 6: slippage prediction + TWAP/VWAP)
8. Execute via broker adapter
9. Update risk tracking

Phase 6 Additions:
- ExecutionManager integration (slippage prediction, TWAP/VWAP scheduling)
- Synchronous Block-and-Skip AI Architecture
- Latency and slippage tracking via ExecutionMetrics

Works with any BrokerAdapter (Upstox, Paper, etc.)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from quantioa.broker.base import BrokerAdapter
from quantioa.data.sample_data import generate_order_book
from quantioa.engine.signal_generator import SignalGenerator, SignalOutput
from quantioa.engine.trade_confirmation import ConfirmationResult, TradeConfirmation
from quantioa.increments.inc1_microstructure import OrderFlowAnalyzer
from quantioa.increments.inc2_volatility import VolatilityRegimeDetector
from quantioa.increments.inc4_kelly import KellyCriterionSizer
from quantioa.increments.inc8_execution import ExecutionManager
from quantioa.indicators.suite import StreamingIndicatorSuite
from quantioa.models.enums import ExecutionStrategy, TradeSide
from quantioa.models.types import (
    ExecutionMetrics,
    IntentToTrade,
    Order,
    Tick,
    TradeResult,
)
from quantioa.risk.framework import RiskFramework

logger = logging.getLogger(__name__)


@dataclass
class LoopStats:
    """Running statistics for the trading loop."""

    ticks_processed: int = 0
    signals_generated: int = 0
    trades_attempted: int = 0
    trades_executed: int = 0
    trades_rejected: int = 0
    stops_hit: int = 0
    total_pnl: float = 0.0

    # Phase 6: Execution Optimization metrics
    avg_execution_latency_us: float = 0.0
    avg_slippage_bps: float = 0.0
    total_slippage_cost: float = 0.0
    twap_orders: int = 0
    vwap_orders: int = 0
    market_orders: int = 0
    limit_orders: int = 0
    _latency_samples: list[float] = field(default_factory=list)
    _slippage_samples: list[float] = field(default_factory=list)

    def record_execution(self, metrics: ExecutionMetrics) -> None:
        """Update running averages with a new execution."""
        if metrics.total_execution_us > 0:
            self._latency_samples.append(metrics.total_execution_us)
            self.avg_execution_latency_us = (
                sum(self._latency_samples) / len(self._latency_samples)
            )
        if metrics.actual_slippage_bps > 0:
            self._slippage_samples.append(metrics.actual_slippage_bps)
            self.avg_slippage_bps = (
                sum(self._slippage_samples) / len(self._slippage_samples)
            )
            self.total_slippage_cost += metrics.predicted_slippage_bps


class TradingLoop:
    """Main trading loop that orchestrates the entire pipeline.

    Usage:
        loop = TradingLoop(broker=paper_adapter, capital=100_000)
        for tick in ticks:
            result = await loop.process_tick(tick)
    """

    def __init__(
        self,
        broker: BrokerAdapter,
        capital: float = 100_000.0,
        symbol: str = "NIFTY50",
        trade_quantity: int = 1,
        min_confidence: float = 0.45,
        atr_multiplier: float = 2.0,
        daily_loss_pct: float = 2.0,
        execution_manager: ExecutionManager | None = None,
    ) -> None:
        self.broker = broker
        self.symbol = symbol
        self.capital = capital
        self.trade_qty = trade_quantity

        # Components
        self.indicators = StreamingIndicatorSuite()
        self.ofi = OrderFlowAnalyzer()
        self.volatility = VolatilityRegimeDetector()
        self.kelly = KellyCriterionSizer()
        self.signal_gen = SignalGenerator()
        self.confirmation = TradeConfirmation(min_confidence=min_confidence)
        self.risk = RiskFramework(
            capital=capital,
            daily_loss_pct=daily_loss_pct,
            atr_multiplier=atr_multiplier,
        )
        self.execution_mgr = execution_manager or ExecutionManager()

        # State
        self.stats = LoopStats()
        self._in_position = False
        self._position_side: str = ""
        self._entry_price: float = 0.0
        self._entry_tick_idx: int = 0
        self._last_signal: SignalOutput | None = None
        self._last_confirmation: ConfirmationResult | None = None
        self._last_execution_metrics: ExecutionMetrics | None = None
        self._trade_counter = 0
        self._needs_fresh_data = False  # Block-and-Skip flag

    async def process_tick(self, tick: Tick) -> dict:
        """Process a single tick through the full pipeline.

        Returns a dict with:
            - action: "ENTRY" | "EXIT" | "HOLD" | "STOPPED"
            - signal: SignalOutput (if generated)
            - confirmation: ConfirmationResult (if checked)
            - pnl: float (if position closed)
        """
        self.stats.ticks_processed += 1
        result: dict = {"action": "HOLD", "tick": tick.close}

        # 1. Update indicators
        snapshot = self.indicators.update(tick)
        # Convert IndicatorSnapshot to dict for signal generator
        ind_values = {
            "rsi": snapshot.rsi,
            "macd_hist": snapshot.macd_hist,
            "macd_line": snapshot.macd_line,
            "macd_signal": snapshot.macd_signal,
            "ema_9": snapshot.ema_9,
            "ema_21": snapshot.ema_21,
            "ema_55": snapshot.ema_55,
            "sma_20": snapshot.sma_20,
            "sma_50": snapshot.sma_50,
            "atr": snapshot.atr,
            "obv": snapshot.obv,
            "vwap": snapshot.vwap,
            "close": tick.close,
        }

        # 2. Update price in broker (for paper trading)
        if hasattr(self.broker, "set_price"):
            self.broker.set_price(tick.symbol, tick.close)

        atr = ind_values["atr"] or tick.close * 0.01  # fallback 1%

        # 3. Check existing position for stop-loss
        if self._in_position:
            stop_hit = self.risk.check_position(tick.symbol, tick.close, atr)
            if stop_hit:
                pnl = await self._close_position(tick, reason="STOP_LOSS")
                result["action"] = "STOPPED"
                result["pnl"] = pnl
                self.stats.stops_hit += 1
                return result

            # Check for exit signal (opposite signal)
            signal = self._generate_signal(ind_values, tick)
            if self._should_exit(signal):
                pnl = await self._close_position(tick, reason="SIGNAL_EXIT")
                result["action"] = "EXIT"
                result["pnl"] = pnl
                result["signal"] = signal
                return result

            result["action"] = "HOLD_POSITION"
            return result

        # 4. Generate signal for new entry
        signal = self._generate_signal(ind_values, tick)
        self._last_signal = signal
        self.stats.signals_generated += 1
        result["signal"] = signal

        # 5. Skip if HOLD
        if signal.signal.value == "HOLD":
            return result

        # 6. Confirm trade
        confirmation = self.confirmation.check(
            signal=signal,
            risk_allowed=self.risk.is_trading_allowed(),
            current_position_count=1 if self._in_position else 0,
        )
        self._last_confirmation = confirmation
        result["confirmation"] = confirmation

        # 7. Execute if approved
        if confirmation.approved:
            await self._open_position(tick, signal, atr)
            result["action"] = "ENTRY"
            self.stats.trades_executed += 1
        else:
            self.stats.trades_rejected += 1

        self.stats.trades_attempted += 1
        return result

    def _generate_signal(self, ind: dict, tick: Tick) -> SignalOutput:
        """Run all increments and generate combined signal."""
        # OFI via synthetic order book from tick data
        bias = (tick.close - tick.open) / max(tick.high - tick.low, 0.01)
        order_book = generate_order_book(
            mid_price=tick.close,
            bias=max(min(bias, 0.8), -0.8),
            base_qty=int(tick.volume / 10),
        )
        ofi_result = self.ofi.analyze(order_book)
        ofi_dict = {
            "signal_strength": ofi_result.imbalance_strength,
            "direction": 1 if ofi_result.ofi > 0 else (-1 if ofi_result.ofi < 0 else 0),
        }

        # Volatility regime
        atr = ind.get("atr", tick.close * 0.01)
        regime_result = self.volatility.detect(atr=atr, close_price=tick.close)
        regime_dict = {
            "regime": regime_result.regime.value,
            "position_multiplier": regime_result.position_size_multiplier,
        }

        # Kelly (uses trade history — returns conservative defaults if not enough history)
        stop_price = tick.close - atr * 2
        kelly_result = self.kelly.calculate(
            capital=self.capital,
            entry_price=tick.close,
            stop_loss_price=stop_price,
        )
        kelly_dict = {
            "kelly_fraction": kelly_result.fractional_kelly,
            "is_active": kelly_result.is_active,
        }

        return self.signal_gen.generate(
            indicators=ind,
            ofi_result=ofi_dict,
            regime_result=regime_dict,
            kelly_result=kelly_dict,
        )

    async def _open_position(self, tick: Tick, signal: SignalOutput, atr: float) -> None:
        """Open a new position using the ExecutionManager.

        Phase 6: Evaluates slippage, selects optimal execution strategy
        (MARKET/LIMIT/TWAP/VWAP), and records execution metrics.
        """
        side = TradeSide.LONG if signal.signal.value == "BUY" else TradeSide.SHORT
        exec_start = time.perf_counter_ns()

        # Phase 6: Evaluate execution strategy via slippage prediction
        order_book = await self.broker.get_order_book_snapshot(tick.symbol)
        atr_pct = (atr / tick.close * 100) if tick.close > 0 else 1.0

        plan = self.execution_mgr.evaluate(
            order_quantity=self.trade_qty,
            order_book=order_book,
            side=side,
            atr_pct=atr_pct,
        )

        metrics = ExecutionMetrics(
            predicted_slippage_bps=plan.predicted_slippage_pct * 100,
        )

        # Execute based on chosen strategy
        if plan.strategy in (ExecutionStrategy.TWAP, ExecutionStrategy.VWAP):
            parent = self.execution_mgr.create_schedule(
                strategy=plan.strategy,
                symbol=tick.symbol,
                side=side,
                total_quantity=self.trade_qty,
                current_price=tick.close,
            )
            # Execute all child orders sequentially
            for child in parent.children:
                child_order = Order(
                    symbol=tick.symbol,
                    side=side,
                    quantity=child.quantity,
                )
                resp = await self.broker.place_order(child_order)
                fill_price = resp.filled_price or tick.close
                self.execution_mgr.record_fill(child, fill_price, child.quantity)
                metrics.broker_latency_ms = max(metrics.broker_latency_ms, resp.latency_ms)

            self.execution_mgr.update_parent(parent)
            actual_price = parent.average_fill_price or tick.close
            metrics.actual_slippage_bps = parent.total_slippage_bps

            if plan.strategy == ExecutionStrategy.TWAP:
                self.stats.twap_orders += 1
            else:
                self.stats.vwap_orders += 1

            logger.info(
                "ENTRY %s %s x%d via %s (%d slices) @ avg ₹%.2f",
                side.value, tick.symbol, self.trade_qty,
                plan.strategy.value, len(parent.children), actual_price,
            )
        else:
            # MARKET or LIMIT — single order
            order = Order(
                symbol=tick.symbol,
                side=side,
                quantity=self.trade_qty,
            )
            resp = await self.broker.place_order(order)
            actual_price = resp.filled_price or tick.close
            metrics.broker_latency_ms = resp.latency_ms

            if resp.filled_price and tick.close > 0:
                metrics.actual_slippage_bps = (
                    abs(resp.filled_price - tick.close) / tick.close * 10_000
                )

            if plan.strategy == ExecutionStrategy.MARKET:
                self.stats.market_orders += 1
            else:
                self.stats.limit_orders += 1

            logger.info(
                "ENTRY %s %s x%d via %s @ ₹%.2f (conf=%.2f)",
                side.value, tick.symbol, self.trade_qty,
                plan.strategy.value, actual_price, signal.confidence,
            )

        # Record execution latency
        exec_end = time.perf_counter_ns()
        metrics.total_execution_us = (exec_end - exec_start) / 1_000
        self._last_execution_metrics = metrics
        self.stats.record_execution(metrics)

        # Warn if latency exceeds 5ms target
        if metrics.broker_latency_ms > 5:
            logger.warning(
                "Broker latency %dms exceeds 5ms target for %s",
                metrics.broker_latency_ms, tick.symbol,
            )

        self._in_position = True
        self._position_side = side.value
        self._entry_price = tick.close
        self._entry_tick_idx = self.stats.ticks_processed
        self._trade_counter += 1

        # Register with risk framework
        self.risk.register_position(tick.symbol, side.value, tick.close, atr)

    async def _close_position(self, tick: Tick, reason: str = "") -> float:
        """Close current position and return P&L."""
        if self._position_side == "LONG":
            pnl = (tick.close - self._entry_price) * self.trade_qty
            side = TradeSide.SHORT  # sell to close
        else:
            pnl = (self._entry_price - tick.close) * self.trade_qty
            side = TradeSide.LONG  # buy to close

        order = Order(symbol=tick.symbol, side=side, quantity=self.trade_qty)
        await self.broker.place_order(order)

        self.risk.record_trade_pnl(pnl)
        self.risk.close_position(tick.symbol)
        self.stats.total_pnl += pnl

        # Record for Kelly criterion
        trade_result = TradeResult(
            id=f"T-{self._trade_counter}",
            symbol=tick.symbol,
            side=TradeSide.LONG if self._position_side == "LONG" else TradeSide.SHORT,
            quantity=self.trade_qty,
            entry_price=self._entry_price,
            exit_price=tick.close,
            entry_time=float(self._entry_tick_idx),
            exit_time=float(self.stats.ticks_processed),
            exit_reason=reason,
        )
        self.kelly.add_trade(trade_result)

        logger.info(
            "EXIT %s %s @ ₹%.2f | P&L: ₹%.2f (%s)",
            self._position_side, tick.symbol, tick.close, pnl, reason,
        )

        self._in_position = False
        self._position_side = ""
        self._entry_price = 0.0

        return pnl

    def _should_exit(self, signal: SignalOutput) -> bool:
        """Check if signal suggests closing current position."""
        if signal.signal.value == "HOLD":
            return False
        if self._position_side == "LONG" and signal.signal.value == "SELL":
            return signal.confidence > 0.4
        if self._position_side == "SHORT" and signal.signal.value == "BUY":
            return signal.confidence > 0.4
        return False

    async def fetch_fresh_tick(self) -> Tick | None:
        """Fetch the absolute latest market snapshot after AI decision.

        Phase 6 Block-and-Skip: Called after the AI returns a decision
        to ensure the next loop iteration uses current data, not the
        stale backlog that accumulated during the 1-2 minute AI call.
        """
        try:
            quote = await self.broker.get_quote(self.symbol)
            return Tick(
                timestamp=quote.timestamp,
                symbol=self.symbol,
                open=quote.price,
                high=quote.price,
                low=quote.price,
                close=quote.price,
                volume=quote.volume,
            )
        except Exception as e:
            logger.error("Failed to fetch fresh tick: %s", e)
            return None

    async def process_ai_intent(self, intent: IntentToTrade) -> dict:
        """Process an AI trading decision using the Block-and-Skip flow.

        1. AI decision arrives (1-2 minutes have passed).
        2. Fetch fresh market data (skip stale ticks).
        3. Re-evaluate all increments with fresh data.
        4. Execute via the ExecutionManager.

        Returns the same result dict as ``process_tick``.
        """
        logger.info(
            "AI intent received: %s %s (conf=%.2f, age=%.1fs)",
            intent.signal.value, intent.symbol,
            intent.confidence, intent.context_age_seconds,
        )

        # Step 1: Fetch absolute latest data
        fresh_tick = await self.fetch_fresh_tick()
        if fresh_tick is None:
            return {"action": "HOLD", "reason": "Failed to fetch fresh data"}

        # Step 2: Update indicators with fresh tick
        snapshot = self.indicators.update(fresh_tick)
        ind_values = {
            "rsi": snapshot.rsi,
            "macd_hist": snapshot.macd_hist,
            "macd_line": snapshot.macd_line,
            "macd_signal": snapshot.macd_signal,
            "ema_9": snapshot.ema_9,
            "ema_21": snapshot.ema_21,
            "ema_55": snapshot.ema_55,
            "sma_20": snapshot.sma_20,
            "sma_50": snapshot.sma_50,
            "atr": snapshot.atr,
            "obv": snapshot.obv,
            "vwap": snapshot.vwap,
            "close": fresh_tick.close,
        }

        # Step 3: Re-run all increments with fresh data
        signal = self._generate_signal(ind_values, fresh_tick)
        atr = ind_values["atr"] or fresh_tick.close * 0.01

        # Step 4: Validate AI intent still aligns with fresh signals
        if signal.signal.value == "HOLD":
            logger.info(
                "AI wanted %s but fresh signals say HOLD — skipping.",
                intent.signal.value,
            )
            return {"action": "HOLD", "reason": "Fresh data contradicts AI intent"}

        # Step 5: Confirm and execute
        confirmation = self.confirmation.check(
            signal=signal,
            risk_allowed=self.risk.is_trading_allowed(),
            current_position_count=1 if self._in_position else 0,
        )

        result: dict = {"action": "HOLD", "tick": fresh_tick.close, "signal": signal}

        if confirmation.approved and not self._in_position:
            await self._open_position(fresh_tick, signal, atr)
            result["action"] = "ENTRY"
            self.stats.trades_executed += 1
        else:
            self.stats.trades_rejected += 1

        self.stats.trades_attempted += 1
        self._needs_fresh_data = True  # Flag: next loop must fetch fresh data
        return result

    def summary(self) -> str:
        return (
            f"=== Trading Loop Summary ===\n"
            f"Ticks:     {self.stats.ticks_processed}\n"
            f"Signals:   {self.stats.signals_generated}\n"
            f"Attempted: {self.stats.trades_attempted}\n"
            f"Executed:  {self.stats.trades_executed}\n"
            f"Rejected:  {self.stats.trades_rejected}\n"
            f"Stops Hit: {self.stats.stops_hit}\n"
            f"Total P&L: ₹{self.stats.total_pnl:,.2f}\n"
            f"Daily P&L: ₹{self.risk.daily_pnl:,.2f}\n"
            f"--- Phase 6 Execution Metrics ---\n"
            f"Avg Latency:  {self.stats.avg_execution_latency_us:,.0f} µs\n"
            f"Avg Slippage: {self.stats.avg_slippage_bps:.1f} bps\n"
            f"MARKET:       {self.stats.market_orders}\n"
            f"LIMIT:        {self.stats.limit_orders}\n"
            f"TWAP:         {self.stats.twap_orders}\n"
            f"VWAP:         {self.stats.vwap_orders}"
        )
