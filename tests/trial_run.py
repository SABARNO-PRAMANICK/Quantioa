#!/usr/bin/env python3
"""
Trial Run — 200-tick simulated trading session with full output.

Run:
    cd /media/sabarno/HDD-EXT4/Quantioa
    PYTHONPATH=src python tests/trial_run.py
"""

from __future__ import annotations

import asyncio
import logging
import sys

# Simple logging — show key trading events
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
# Quiet down noisy sub-loggers
for name in ("quantioa.indicators", "quantioa.increments", "quantioa.risk"):
    logging.getLogger(name).setLevel(logging.WARNING)

from quantioa.broker.paper_adapter import PaperTradingAdapter
from quantioa.data.sample_data import generate_ticks
from quantioa.engine.trading_loop import TradingLoop


async def main() -> None:
    print("=" * 60)
    print("  Quantioa — Trial Trading Run (Paper Mode)")
    print("=" * 60)
    print()

    # Config
    N_TICKS = 200
    CAPITAL = 100_000.0
    TRADE_QTY = 10

    # Generate sample market data
    ticks = generate_ticks(
        symbol="NIFTY50",
        n=N_TICKS,
        start_price=22000.0,
        volatility=0.003,
        trend=0.0001,
        seed=42,
    )

    print(f"Generated {len(ticks)} ticks")
    print(f"Price range: ₹{min(t.close for t in ticks):,.2f} – ₹{max(t.close for t in ticks):,.2f}")
    print(f"Capital: ₹{CAPITAL:,.0f}")
    print(f"Trade quantity: {TRADE_QTY}")
    print()

    # Setup
    broker = PaperTradingAdapter(initial_capital=CAPITAL)
    await broker.connect()

    loop = TradingLoop(
        broker=broker,
        capital=CAPITAL,
        trade_quantity=TRADE_QTY,
        min_confidence=0.40,
        atr_multiplier=2.0,
        daily_loss_pct=3.0,
    )

    # Process all ticks
    print("─" * 60)
    print("  TRADING LOG")
    print("─" * 60)

    entries = []
    exits = []

    for i, tick in enumerate(ticks):
        result = await loop.process_tick(tick)

        action = result["action"]
        if action == "ENTRY":
            entries.append((i, tick.close, result.get("signal")))
        elif action in ("EXIT", "STOPPED"):
            pnl = result.get("pnl", 0)
            exits.append((i, tick.close, pnl, action))

    # Summary
    print()
    print("─" * 60)
    print("  RESULTS")
    print("─" * 60)
    print()
    print(loop.summary())
    print()
    print(broker.summary())

    # Trade log
    if entries or exits:
        print()
        print("─" * 60)
        print("  TRADE LOG")
        print("─" * 60)
        print(f"{'#':>3} {'Tick':>5} {'Action':>8} {'Price':>10} {'P&L':>10}")
        print("-" * 42)
        all_events = [(t, p, "ENTRY", 0) for t, p, _ in entries] + \
                     [(t, p, a, pnl) for t, p, pnl, a in exits]
        all_events.sort(key=lambda x: x[0])
        for idx, (t, price, action, pnl) in enumerate(all_events, 1):
            pnl_str = f"₹{pnl:+,.2f}" if pnl else ""
            print(f"{idx:>3} {t:>5} {action:>8} ₹{price:>9,.2f} {pnl_str:>10}")

    print()
    print("=" * 60)
    print("  Trial run complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
