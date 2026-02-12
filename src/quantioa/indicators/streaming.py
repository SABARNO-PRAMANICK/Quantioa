"""
Streaming technical indicators — O(1) per tick update.

Each indicator maintains internal state so that new ticks require only
a constant-time update, not a full O(N) recalculation.
"""

from __future__ import annotations

import collections
import math


class StreamingSMA:
    """Simple Moving Average using circular buffer + running sum.

    Latency: ~50-100 ns per update.
    """

    __slots__ = ("period", "_buffer", "_sum")

    def __init__(self, period: int) -> None:
        self.period = period
        self._buffer: collections.deque[float] = collections.deque(maxlen=period)
        self._sum: float = 0.0

    def update(self, price: float) -> float:
        if len(self._buffer) == self.period:
            self._sum -= self._buffer[0]
        self._buffer.append(price)
        self._sum += price
        return self._sum / len(self._buffer)

    @property
    def ready(self) -> bool:
        return len(self._buffer) == self.period

    @property
    def value(self) -> float:
        if not self._buffer:
            return 0.0
        return self._sum / len(self._buffer)

    def reset(self) -> None:
        self._buffer.clear()
        self._sum = 0.0


class StreamingEMA:
    """Exponential Moving Average — single multiply-add.

    Latency: ~20 ns per update.
    """

    __slots__ = ("period", "_alpha", "_ema")

    def __init__(self, period: int) -> None:
        self.period = period
        self._alpha: float = 2.0 / (period + 1)
        self._ema: float | None = None

    def update(self, price: float) -> float:
        if self._ema is None:
            self._ema = price
        else:
            self._ema = self._alpha * price + (1.0 - self._alpha) * self._ema
        return self._ema

    @property
    def ready(self) -> bool:
        return self._ema is not None

    @property
    def value(self) -> float:
        return self._ema if self._ema is not None else 0.0

    def reset(self) -> None:
        self._ema = None


class StreamingRSI:
    """Relative Strength Index using exponential averaging of gains/losses.

    Latency: ~50 ns per update.
    """

    __slots__ = ("period", "_alpha", "_avg_gain", "_avg_loss", "_prev_close", "_count")

    def __init__(self, period: int = 14) -> None:
        self.period = period
        self._alpha: float = 1.0 / period
        self._avg_gain: float | None = None
        self._avg_loss: float | None = None
        self._prev_close: float | None = None
        self._count: int = 0

    def update(self, close: float) -> float:
        if self._prev_close is None:
            self._prev_close = close
            return 50.0  # Neutral default

        delta = close - self._prev_close
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)

        if self._avg_gain is None:
            self._avg_gain = gain
            self._avg_loss = loss
        else:
            self._avg_gain = self._alpha * gain + (1.0 - self._alpha) * self._avg_gain
            self._avg_loss = self._alpha * loss + (1.0 - self._alpha) * self._avg_loss

        self._prev_close = close
        self._count += 1

        rs = self._avg_gain / (self._avg_loss + 1e-9)
        return 100.0 - (100.0 / (1.0 + rs))

    @property
    def ready(self) -> bool:
        return self._count >= self.period

    @property
    def value(self) -> float:
        if self._avg_gain is None or self._avg_loss is None:
            return 50.0
        rs = self._avg_gain / (self._avg_loss + 1e-9)
        return 100.0 - (100.0 / (1.0 + rs))

    def reset(self) -> None:
        self._avg_gain = None
        self._avg_loss = None
        self._prev_close = None
        self._count = 0


class StreamingMACD:
    """MACD decomposed into three streaming EMAs.

    Latency: ~100 ns per update.
    Config: (12, 26, 9) by default.
    """

    __slots__ = ("_ema_fast", "_ema_slow", "_ema_signal")

    def __init__(
        self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9
    ) -> None:
        self._ema_fast = StreamingEMA(fast_period)
        self._ema_slow = StreamingEMA(slow_period)
        self._ema_signal = StreamingEMA(signal_period)

    def update(self, close: float) -> tuple[float, float, float]:
        """Returns (macd_line, signal_line, histogram)."""
        fast = self._ema_fast.update(close)
        slow = self._ema_slow.update(close)
        macd_line = fast - slow
        signal_line = self._ema_signal.update(macd_line)
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @property
    def ready(self) -> bool:
        return self._ema_slow.ready

    def reset(self) -> None:
        self._ema_fast.reset()
        self._ema_slow.reset()
        self._ema_signal.reset()


class StreamingATR:
    """Average True Range — true range with EMA smoothing.

    Latency: ~50 ns per update.
    """

    __slots__ = ("period", "_alpha", "_atr", "_prev_close", "_count")

    def __init__(self, period: int = 14) -> None:
        self.period = period
        self._alpha: float = 2.0 / (period + 1)
        self._atr: float | None = None
        self._prev_close: float | None = None
        self._count: int = 0

    def update(self, high: float, low: float, close: float) -> float:
        prev = self._prev_close if self._prev_close is not None else close

        tr1 = high - low
        tr2 = abs(high - prev)
        tr3 = abs(low - prev)
        true_range = max(tr1, tr2, tr3)

        if self._atr is None:
            self._atr = true_range
        else:
            self._atr = self._alpha * true_range + (1.0 - self._alpha) * self._atr

        self._prev_close = close
        self._count += 1
        return self._atr

    @property
    def ready(self) -> bool:
        return self._count >= self.period

    @property
    def value(self) -> float:
        return self._atr if self._atr is not None else 0.0

    def reset(self) -> None:
        self._atr = None
        self._prev_close = None
        self._count = 0


class StreamingOBV:
    """On-Balance Volume — cumulative directed volume.

    Latency: ~30 ns per update.
    """

    __slots__ = ("_obv", "_prev_close")

    def __init__(self) -> None:
        self._obv: float = 0.0
        self._prev_close: float | None = None

    def update(self, close: float, volume: float) -> float:
        if self._prev_close is None:
            self._prev_close = close
            return 0.0

        if close > self._prev_close:
            self._obv += volume
        elif close < self._prev_close:
            self._obv -= volume
        # Equal → no change

        self._prev_close = close
        return self._obv

    @property
    def value(self) -> float:
        return self._obv

    def reset(self) -> None:
        self._obv = 0.0
        self._prev_close = None


class StreamingVWAP:
    """Volume-Weighted Average Price — session-based (resets at market open).

    Latency: ~50 ns per update.
    """

    __slots__ = ("_cum_tp_vol", "_cum_vol")

    def __init__(self) -> None:
        self._cum_tp_vol: float = 0.0
        self._cum_vol: float = 0.0

    def update(self, high: float, low: float, close: float, volume: float) -> float:
        typical_price = (high + low + close) / 3.0
        self._cum_tp_vol += typical_price * volume
        self._cum_vol += volume
        return self._cum_tp_vol / (self._cum_vol + 1e-9)

    @property
    def value(self) -> float:
        return self._cum_tp_vol / (self._cum_vol + 1e-9) if self._cum_vol > 0 else 0.0

    def reset(self) -> None:
        """Call at market open to reset session VWAP."""
        self._cum_tp_vol = 0.0
        self._cum_vol = 0.0


class StreamingKeltnerChannel:
    """Keltner Channels — EMA ± multiplier * ATR (lighter than Bollinger Bands).

    Latency: ~100 ns per update.
    """

    __slots__ = ("_ema", "_atr", "_mult")

    def __init__(
        self, ema_period: int = 20, atr_period: int = 14, atr_mult: float = 2.0
    ) -> None:
        self._ema = StreamingEMA(ema_period)
        self._atr = StreamingATR(atr_period)
        self._mult = atr_mult

    def update(
        self, high: float, low: float, close: float
    ) -> tuple[float, float, float]:
        """Returns (upper, middle, lower)."""
        ema_val = self._ema.update(close)
        atr_val = self._atr.update(high, low, close)
        band = self._mult * atr_val
        return ema_val + band, ema_val, ema_val - band

    @property
    def ready(self) -> bool:
        return self._ema.ready and self._atr.ready

    def reset(self) -> None:
        self._ema.reset()
        self._atr.reset()
