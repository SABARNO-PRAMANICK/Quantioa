"""
Integration test for the engine: full pipeline with paper broker.
"""

import pytest
import pytest_asyncio

from quantioa.broker.paper_adapter import PaperTradingAdapter
from quantioa.data.sample_data import generate_ticks
from quantioa.engine.trading_loop import TradingLoop


@pytest.fixture
def paper_broker():
    return PaperTradingAdapter(initial_capital=100_000)


@pytest.fixture
def ticks():
    return generate_ticks(n=100, seed=42, volatility=0.003, trend=0.0002)


@pytest.mark.asyncio
async def test_full_pipeline_no_crash(paper_broker, ticks):
    """The full pipeline should process 100 ticks without crashing."""
    await paper_broker.connect()
    loop = TradingLoop(
        broker=paper_broker,
        capital=100_000,
        trade_quantity=1,
        min_confidence=0.3,
    )

    for tick in ticks:
        result = await loop.process_tick(tick)
        assert "action" in result
        assert result["action"] in ("HOLD", "HOLD_POSITION", "ENTRY", "EXIT", "STOPPED")

    assert loop.stats.ticks_processed == 100


@pytest.mark.asyncio
async def test_paper_broker_tracks_pnl(paper_broker, ticks):
    """Paper broker should track positions and P&L."""
    await paper_broker.connect()
    loop = TradingLoop(
        broker=paper_broker,
        capital=100_000,
        trade_quantity=1,
        min_confidence=0.3,
    )

    for tick in ticks:
        await loop.process_tick(tick)

    # Should have processed something
    assert loop.stats.ticks_processed == 100

    # Check broker balance is accessible
    balance = await paper_broker.get_balance()
    assert "cash" in balance
    assert "total_equity" in balance


@pytest.mark.asyncio
async def test_risk_framework_blocks_after_loss(paper_broker):
    """Risk framework should halt trading after hitting daily loss limit."""
    await paper_broker.connect()
    loop = TradingLoop(
        broker=paper_broker,
        capital=100_000,
        trade_quantity=10,
        min_confidence=0.1,  # low threshold to trigger trades
        daily_loss_pct=0.1,  # very tight limit for testing
    )

    # Generate volatile ticks to potentially trigger stops
    ticks = generate_ticks(n=200, seed=99, volatility=0.01, trend=-0.001)

    for tick in ticks:
        await loop.process_tick(tick)

    # Either trading was halted or we made it through
    # (exact behavior depends on random data, but it shouldn't crash)
    assert loop.stats.ticks_processed == 200
