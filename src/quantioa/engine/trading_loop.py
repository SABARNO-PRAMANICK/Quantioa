"""
Trading Loop — the main orchestrator.

Each cycle:
1. Receive tick data
2. Update indicators
3. Run increments (OFI, volatility, Kelly)
4. Generate signal
5. Check risk
6. Confirm trade
7. Execute via broker adapter
8. Update risk tracking

Works with any BrokerAdapter (Upstox, Paper, etc.)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from quantioa.broker.base import BrokerAdapter
from quantioa.data.sample_data import generate_order_book
from quantioa.engine.signal_generator import SignalGenerator, SignalOutput
from quantioa.engine.trade_confirmation import ConfirmationResult, TradeConfirmation
from quantioa.increments.inc1_microstructure import OrderFlowAnalyzer
from quantioa.increments.inc2_volatility import VolatilityRegimeDetector
from quantioa.increments.inc4_kelly import KellyCriterionSizer
from quantioa.indicators.suite import StreamingIndicatorSuite
from quantioa.models.enums import TradeSide
from quantioa.models.types import Order, Tick, TradeResult
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

        # State
        self.stats = LoopStats()
        self._in_position = False
        self._position_side: str = ""
        self._entry_price: float = 0.0
        self._entry_tick_idx: int = 0
        self._last_signal: SignalOutput | None = None
        self._last_confirmation: ConfirmationResult | None = None
        self._trade_counter = 0

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
        """Open a new position."""
        side = TradeSide.LONG if signal.signal.value == "BUY" else TradeSide.SHORT

        order = Order(
            symbol=tick.symbol,
            side=side,
            quantity=self.trade_qty,
        )
        await self.broker.place_order(order)

        self._in_position = True
        self._position_side = side.value
        self._entry_price = tick.close
        self._entry_tick_idx = self.stats.ticks_processed
        self._trade_counter += 1

        # Register with risk framework
        self.risk.register_position(tick.symbol, side.value, tick.close, atr)

        logger.info(
            "ENTRY %s %s x%d @ ₹%.2f (conf=%.2f)",
            side.value, tick.symbol, self.trade_qty, tick.close, signal.confidence,
        )

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
            f"Daily P&L: ₹{self.risk.daily_pnl:,.2f}"
        )
