"""
StreamingIndicatorSuite — aggregates all streaming indicators into a single
update() call that returns a complete snapshot of indicator values + binary signals.

Total latency target: <500µs for full suite update.
"""

from __future__ import annotations

import collections

from quantioa.indicators.streaming import (
    StreamingATR,
    StreamingEMA,
    StreamingKeltnerChannel,
    StreamingMACD,
    StreamingOBV,
    StreamingRSI,
    StreamingSMA,
    StreamingVWAP,
)
from quantioa.models.types import IndicatorSnapshot, Tick


class StreamingIndicatorSuite:
    """Compute all indicators in O(1) per tick.

    Updates 8 indicator types (15 instances) on each tick and returns
    a unified ``IndicatorSnapshot`` with raw values and binary signals
    for downstream signal generators.
    """

    def __init__(self) -> None:
        # Trend
        self.sma_20 = StreamingSMA(20)
        self.sma_50 = StreamingSMA(50)
        self.ema_9 = StreamingEMA(9)
        self.ema_21 = StreamingEMA(21)
        self.ema_55 = StreamingEMA(55)

        # Momentum
        self.rsi = StreamingRSI(14)
        self.macd = StreamingMACD()

        # Volatility
        self.atr = StreamingATR(14)
        self.keltner = StreamingKeltnerChannel()

        # Volume
        self.obv = StreamingOBV()
        self.vwap = StreamingVWAP()

        # Price history for higher-order features
        self.close_history: collections.deque[float] = collections.deque(maxlen=50)
        self._tick_count: int = 0

    def update(self, tick: Tick) -> IndicatorSnapshot:
        """Update all indicators with a new tick and return a full snapshot."""
        self.close_history.append(tick.close)
        self._tick_count += 1

        # ── Trend ──
        sma_20 = self.sma_20.update(tick.close)
        sma_50 = self.sma_50.update(tick.close)
        ema_9 = self.ema_9.update(tick.close)
        ema_21 = self.ema_21.update(tick.close)
        ema_55 = self.ema_55.update(tick.close)

        # ── Momentum ──
        rsi = self.rsi.update(tick.close)
        macd_line, macd_signal, macd_hist = self.macd.update(tick.close)

        # ── Volatility ──
        atr = self.atr.update(tick.high, tick.low, tick.close)
        keltner_upper, keltner_mid, keltner_lower = self.keltner.update(
            tick.high, tick.low, tick.close
        )

        # ── Volume ──
        obv = self.obv.update(tick.close, tick.volume)
        vwap = self.vwap.update(tick.high, tick.low, tick.close, tick.volume)

        # ── Binary Signals ──
        return IndicatorSnapshot(
            sma_20=sma_20,
            sma_50=sma_50,
            ema_9=ema_9,
            ema_21=ema_21,
            ema_55=ema_55,
            rsi=rsi,
            macd_line=macd_line,
            macd_signal=macd_signal,
            macd_hist=macd_hist,
            atr=atr,
            keltner_upper=keltner_upper,
            keltner_mid=keltner_mid,
            keltner_lower=keltner_lower,
            obv=obv,
            vwap=vwap,
            signal_price_above_sma20=1 if tick.close > sma_20 else 0,
            signal_ema_9_gt_21=1 if ema_9 > ema_21 else 0,
            signal_macd_positive=1 if macd_line > 0 else 0,
            signal_rsi_oversold=1 if rsi < 30 else 0,
            signal_rsi_overbought=1 if rsi > 70 else 0,
            signal_price_above_vwap=1 if tick.close > vwap else 0,
        )

    @property
    def ready(self) -> bool:
        """True once enough ticks have passed for all indicators to be meaningful."""
        return self._tick_count >= 55  # Longest EMA period

    def reset_session(self) -> None:
        """Reset session-based indicators (VWAP). Call at market open."""
        self.vwap.reset()

    def reset_all(self) -> None:
        """Full reset of all indicators."""
        self.sma_20.reset()
        self.sma_50.reset()
        self.ema_9.reset()
        self.ema_21.reset()
        self.ema_55.reset()
        self.rsi.reset()
        self.macd.reset()
        self.atr.reset()
        self.keltner.reset()
        self.obv.reset()
        self.vwap.reset()
        self.close_history.clear()
        self._tick_count = 0
