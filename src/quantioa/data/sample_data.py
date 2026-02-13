"""
Sample market data generator for testing.

Produces realistic OHLCV ticks with configurable trend, volatility,
and volume patterns — no external data needed.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from quantioa.models.types import OrderBookLevel, OrderBookSnapshot, Tick


def generate_ticks(
    symbol: str = "NIFTY50",
    n: int = 200,
    start_price: float = 22000.0,
    volatility: float = 0.002,
    trend: float = 0.0001,
    base_volume: int = 5000,
    seed: int | None = 42,
) -> list[Tick]:
    """Generate a sequence of realistic OHLCV ticks.

    Args:
        symbol: Instrument symbol.
        n: Number of ticks to generate.
        start_price: Starting close price.
        volatility: Per-tick volatility (std dev of returns).
        trend: Drift per tick (+ve = uptrend, -ve = downtrend).
        base_volume: Average volume per tick.
        seed: Random seed for reproducibility.

    Returns:
        List of Tick objects with realistic OHLCV values.
    """
    if seed is not None:
        random.seed(seed)

    ticks: list[Tick] = []
    price = start_price

    for i in range(n):
        # Log-normal return with drift
        ret = trend + volatility * random.gauss(0, 1)
        price *= math.exp(ret)

        # OHLC from close
        spread = price * volatility * 1.5
        high = price + abs(random.gauss(0, spread))
        low = price - abs(random.gauss(0, spread))
        open_price = price + random.gauss(0, spread * 0.3)

        # Volume with some randomness + mean-reversion spikes
        vol_mult = 1.0 + 0.5 * abs(ret / volatility)  # higher vol on big moves
        volume = int(base_volume * vol_mult * random.uniform(0.5, 1.5))

        ticks.append(Tick(
            timestamp=float(i),
            symbol=symbol,
            open=round(open_price, 2),
            high=round(max(high, open_price, price), 2),
            low=round(min(low, open_price, price), 2),
            close=round(price, 2),
            volume=max(volume, 100),
        ))

    return ticks


def generate_order_book(
    mid_price: float,
    levels: int = 5,
    spread_pct: float = 0.001,
    base_qty: int = 1000,
    bias: float = 0.0,
) -> OrderBookSnapshot:
    """Generate a synthetic order book around a mid price.

    Args:
        mid_price: Current mid price.
        levels: Number of bid/ask levels.
        spread_pct: Half-spread as fraction of price.
        base_qty: Base quantity per level.
        bias: Positive = more buy volume, negative = more sell volume.

    Returns:
        OrderBookSnapshot with bids and asks.
    """
    half_spread = mid_price * spread_pct
    tick_size = half_spread * 0.5

    bids = []
    asks = []

    for i in range(levels):
        bid_price = round(mid_price - half_spread - i * tick_size, 2)
        ask_price = round(mid_price + half_spread + i * tick_size, 2)

        # Bias adjusts volume: positive → accumulation (more bids)
        bid_qty = int(base_qty * (1.0 + bias) * random.uniform(0.5, 1.5) / (1 + i * 0.2))
        ask_qty = int(base_qty * (1.0 - bias) * random.uniform(0.5, 1.5) / (1 + i * 0.2))

        bids.append(OrderBookLevel(price=bid_price, quantity=max(bid_qty, 10)))
        asks.append(OrderBookLevel(price=ask_price, quantity=max(ask_qty, 10)))

    return OrderBookSnapshot(
        symbol="NIFTY50",
        bids=bids,
        asks=asks,
        timestamp=0.0,
    )
