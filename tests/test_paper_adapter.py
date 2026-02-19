"""
Unit tests for the PaperTradingAdapter.

Tests: connect/disconnect, place order, close position, PnL tracking,
       modify_order, get_order_status, get_positions, get_balance, get_trades.
"""

import pytest

from quantioa.broker.paper_adapter import PaperTradingAdapter
from quantioa.models.enums import OrderStatus, TradeSide
from quantioa.models.types import Order


@pytest.fixture
def broker():
    return PaperTradingAdapter(initial_capital=100_000)


class TestConnectDisconnect:
    @pytest.mark.asyncio
    async def test_connect(self, broker):
        await broker.connect()
        assert broker._connected is True

    @pytest.mark.asyncio
    async def test_disconnect(self, broker):
        await broker.connect()
        await broker.disconnect()
        assert broker._connected is False


class TestPlaceOrder:
    @pytest.mark.asyncio
    async def test_open_long_position(self, broker):
        await broker.connect()
        broker.set_price("NIFTY50", 22000.0)

        order = Order(symbol="NIFTY50", side=TradeSide.LONG, quantity=1, price=22000.0)
        resp = await broker.place_order(order)

        assert resp.status == OrderStatus.FILLED
        assert resp.order_id.startswith("PAPER-")
        assert resp.filled_price == 22000.0
        assert resp.filled_quantity == 1

    @pytest.mark.asyncio
    async def test_open_short_position(self, broker):
        await broker.connect()
        broker.set_price("NIFTY50", 22000.0)

        order = Order(symbol="NIFTY50", side=TradeSide.SHORT, quantity=1)
        resp = await broker.place_order(order)

        assert resp.status == OrderStatus.FILLED
        assert resp.side == TradeSide.SHORT


class TestClosePosition:
    @pytest.mark.asyncio
    async def test_close_long_tracks_pnl(self, broker):
        await broker.connect()
        broker.set_price("NIFTY50", 22000.0)

        # Open long
        await broker.place_order(
            Order(symbol="NIFTY50", side=TradeSide.LONG, quantity=1)
        )

        # Close at higher price
        broker.set_price("NIFTY50", 22100.0)
        await broker.place_order(
            Order(symbol="NIFTY50", side=TradeSide.SHORT, quantity=1)
        )

        # Position should be closed
        positions = await broker.get_positions()
        assert len(positions) == 0
        assert broker._realized_pnl == 100.0

    @pytest.mark.asyncio
    async def test_close_short_tracks_pnl(self, broker):
        await broker.connect()
        broker.set_price("NIFTY50", 22000.0)

        # Open short
        await broker.place_order(
            Order(symbol="NIFTY50", side=TradeSide.SHORT, quantity=2)
        )

        # Close at lower price (profit for short)
        broker.set_price("NIFTY50", 21900.0)
        await broker.place_order(
            Order(symbol="NIFTY50", side=TradeSide.LONG, quantity=2)
        )

        assert broker._realized_pnl == 200.0  # (22000-21900)*2


class TestPositions:
    @pytest.mark.asyncio
    async def test_get_positions(self, broker):
        await broker.connect()
        broker.set_price("NIFTY50", 22000.0)

        await broker.place_order(
            Order(symbol="NIFTY50", side=TradeSide.LONG, quantity=5)
        )

        positions = await broker.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "NIFTY50"
        assert positions[0].side == TradeSide.LONG
        assert positions[0].quantity == 5


class TestBalance:
    @pytest.mark.asyncio
    async def test_initial_balance(self, broker):
        await broker.connect()
        balance = await broker.get_balance()
        assert balance["cash"] == 100_000
        assert balance["total_equity"] == 100_000
        assert balance["realized_pnl"] == 0.0

    @pytest.mark.asyncio
    async def test_balance_after_trade(self, broker):
        await broker.connect()
        broker.set_price("NIFTY50", 22000.0)

        await broker.place_order(
            Order(symbol="NIFTY50", side=TradeSide.LONG, quantity=1)
        )

        balance = await broker.get_balance()
        assert balance["cash"] == 100_000 - 22000.0

    @pytest.mark.asyncio
    async def test_get_account_balance(self, broker):
        await broker.connect()
        assert await broker.get_account_balance() == 100_000


class TestQuote:
    @pytest.mark.asyncio
    async def test_get_quote(self, broker):
        await broker.connect()
        broker.set_price("NIFTY50", 22000.0)

        quote = await broker.get_quote("NIFTY50")
        assert quote.symbol == "NIFTY50"
        assert quote.price == 22000.0
        assert quote.bid < quote.price
        assert quote.ask > quote.price


class TestModifyOrder:
    @pytest.mark.asyncio
    async def test_modify_existing_order(self, broker):
        await broker.connect()
        broker.set_price("TEST", 100.0)

        resp = await broker.place_order(
            Order(symbol="TEST", side=TradeSide.LONG, quantity=1)
        )
        order_id = resp.order_id

        modified = await broker.modify_order(order_id, quantity=5)
        assert modified.order_id == order_id
        assert modified.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_modify_nonexistent_order(self, broker):
        await broker.connect()
        resp = await broker.modify_order("NONEXISTENT", price=100.0)
        assert resp.status == OrderStatus.REJECTED


class TestOrderStatus:
    @pytest.mark.asyncio
    async def test_get_order_status(self, broker):
        await broker.connect()
        broker.set_price("TEST", 100.0)

        resp = await broker.place_order(
            Order(symbol="TEST", side=TradeSide.LONG, quantity=1)
        )

        status = await broker.get_order_status(resp.order_id)
        assert status.order_id == resp.order_id
        assert status.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_get_order_status_unknown(self, broker):
        await broker.connect()
        status = await broker.get_order_status("UNKNOWN")
        assert status.status == OrderStatus.REJECTED


class TestTradesAndOrderBook:
    @pytest.mark.asyncio
    async def test_get_trades(self, broker):
        await broker.connect()
        broker.set_price("TEST", 100.0)

        await broker.place_order(
            Order(symbol="TEST", side=TradeSide.LONG, quantity=1)
        )

        trades = await broker.get_trades()
        assert len(trades) == 1
        assert trades[0]["symbol"] == "TEST"

    @pytest.mark.asyncio
    async def test_get_order_book(self, broker):
        await broker.connect()
        broker.set_price("TEST", 100.0)

        await broker.place_order(
            Order(symbol="TEST", side=TradeSide.LONG, quantity=1)
        )

        orders = await broker.get_order_book()
        assert len(orders) == 1
        assert orders[0].status == OrderStatus.FILLED


class TestSummary:
    @pytest.mark.asyncio
    async def test_summary_string(self, broker):
        await broker.connect()
        summary = broker.summary()
        assert "Paper Trading Summary" in summary
        assert "₹100,000" in summary
