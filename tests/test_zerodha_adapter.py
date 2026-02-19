"""
Unit tests for the Zerodha Kite Connect broker adapter.

Tests: connect, get_quote, get_order_book_snapshot, place_order, modify_order,
       cancel_order, get_positions, get_holdings, get_account_balance,
       get_order_book, get_trades.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
import httpx

from quantioa.broker.zerodha_adapter import (
    ZerodhaAdapter,
    ZerodhaConnectionError,
    ZerodhaAPIError,
)
from quantioa.broker.types import TokenPair
from quantioa.models.enums import OrderStatus, OrderType, TradeSide, ProductType, OrderValidity
from quantioa.models.types import Order


@pytest.fixture
def mock_token_store():
    store = MagicMock()
    store.load.return_value = TokenPair(
        access_token="valid_token",
        expires_at=20000000000.0,
        user_id="USER123",
        exchanges=["NSE"],
        products=["CNC"],
    )
    return store


@pytest.fixture
def adapter(mock_token_store):
    return ZerodhaAdapter(user_id="USER123", token_store=mock_token_store)


def make_response(status_code, json_data):
    resp = httpx.Response(status_code, json=json_data)
    resp.request = httpx.Request("GET", "https://mock")
    return resp


# ── Connect ──────────────────────────────────────────────────────────────


class TestConnect:
    @pytest.mark.asyncio
    async def test_connect_loads_token(self, adapter, mock_token_store):
        await adapter.connect()
        assert adapter._token.access_token == "valid_token"
        mock_token_store.load.assert_called_with("USER123", "ZERODHA")

    @pytest.mark.asyncio
    async def test_connect_no_token_raises(self, mock_token_store):
        mock_token_store.load.return_value = None
        adapter = ZerodhaAdapter(user_id="USER123", token_store=mock_token_store)
        with pytest.raises(ZerodhaConnectionError, match="No Zerodha token"):
            await adapter.connect()

    @pytest.mark.asyncio
    async def test_connect_expired_token_raises(self, mock_token_store):
        mock_token_store.load.return_value = TokenPair(
            access_token="expired",
            expires_at=0.0,  # Already expired
        )
        adapter = ZerodhaAdapter(user_id="USER123", token_store=mock_token_store)
        with pytest.raises(ZerodhaConnectionError, match="expired"):
            await adapter.connect()


# ── Quotes ───────────────────────────────────────────────────────────────


class TestGetQuote:
    @pytest.mark.asyncio
    async def test_get_quote(self, adapter):
        await adapter.connect()

        quote_response = {
            "status": "success",
            "data": {
                "NSE:INFY": {
                    "instrument_token": 408065,
                    "last_price": 1500.0,
                    "volume": 10000,
                    "ohlc": {"open": 1490.0, "high": 1510.0, "low": 1490.0, "close": 1495.0},
                    "depth": {
                        "buy": [{"price": 1499.0, "quantity": 100, "orders": 5}],
                        "sell": [{"price": 1501.0, "quantity": 50, "orders": 2}],
                    },
                }
            },
        }
        adapter._http.request = AsyncMock(return_value=make_response(200, quote_response))

        quote = await adapter.get_quote("NSE:INFY")

        assert quote.symbol == "NSE:INFY"
        assert quote.price == 1500.0
        assert quote.bid == 1499.0
        assert quote.ask == 1501.0
        assert quote.volume == 10000


class TestOrderBookSnapshot:
    @pytest.mark.asyncio
    async def test_get_order_book_snapshot(self, adapter):
        await adapter.connect()

        data = {
            "status": "success",
            "data": {
                "NSE:INFY": {
                    "depth": {
                        "buy": [
                            {"price": 1499.0, "quantity": 100, "orders": 5},
                            {"price": 1498.0, "quantity": 200, "orders": 3},
                        ],
                        "sell": [
                            {"price": 1501.0, "quantity": 50, "orders": 2},
                        ],
                    }
                }
            },
        }
        adapter._http.request = AsyncMock(return_value=make_response(200, data))

        snapshot = await adapter.get_order_book_snapshot("NSE:INFY")

        assert snapshot.symbol == "NSE:INFY"
        assert len(snapshot.bids) == 2
        assert len(snapshot.asks) == 1
        assert snapshot.bids[0].price == 1499.0
        assert snapshot.bids[0].quantity == 100


# ── Orders ───────────────────────────────────────────────────────────────


class TestPlaceOrder:
    @pytest.mark.asyncio
    async def test_place_order_success(self, adapter):
        await adapter.connect()

        order_response = {"status": "success", "data": {"order_id": "ORDER123"}}

        order = Order(
            symbol="NSE:INFY",
            side=TradeSide.LONG,
            quantity=10,
            price=1500.0,
            order_type=OrderType.LIMIT,
            product=ProductType.DELIVERY,
            validity=OrderValidity.DAY,
        )

        adapter._http.request = AsyncMock(return_value=make_response(200, order_response))

        resp = await adapter.place_order(order)

        assert resp.order_id == "ORDER123"
        assert resp.status == OrderStatus.PENDING

        # Verify payload structure
        args, kwargs = adapter._http.request.call_args
        assert args[0] == "POST"
        payload = kwargs["data"]
        assert payload["exchange"] == "NSE"
        assert payload["tradingsymbol"] == "INFY"
        assert payload["transaction_type"] == "BUY"
        assert payload["product"] == "CNC"

    @pytest.mark.asyncio
    async def test_place_order_sell(self, adapter):
        await adapter.connect()
        adapter._http.request = AsyncMock(
            return_value=make_response(200, {"status": "success", "data": {"order_id": "S1"}})
        )

        order = Order(symbol="NSE:SBIN", side=TradeSide.SHORT, quantity=5)
        resp = await adapter.place_order(order)

        assert resp.order_id == "S1"
        args, kwargs = adapter._http.request.call_args
        assert kwargs["data"]["transaction_type"] == "SELL"

    @pytest.mark.asyncio
    async def test_place_order_api_error(self, adapter):
        await adapter.connect()
        adapter._http.request = AsyncMock(
            return_value=make_response(200, {"status": "error", "message": "Insufficient margin"})
        )

        order = Order(symbol="NSE:INFY", side=TradeSide.LONG, quantity=100)
        resp = await adapter.place_order(order)
        assert resp.status == OrderStatus.REJECTED

    @pytest.mark.asyncio
    async def test_place_order_no_exchange_prefix(self, adapter):
        """Symbol without colon should default to NSE."""
        await adapter.connect()
        adapter._http.request = AsyncMock(
            return_value=make_response(200, {"status": "success", "data": {"order_id": "O2"}})
        )
        order = Order(symbol="INFY", side=TradeSide.LONG, quantity=1)
        await adapter.place_order(order)

        args, kwargs = adapter._http.request.call_args
        assert kwargs["data"]["exchange"] == "NSE"
        assert kwargs["data"]["tradingsymbol"] == "INFY"


class TestModifyOrder:
    @pytest.mark.asyncio
    async def test_modify_order_success(self, adapter):
        await adapter.connect()
        adapter._http.request = AsyncMock(
            return_value=make_response(200, {"status": "success"})
        )

        resp = await adapter.modify_order("ORDER123", quantity=20, price=1510.0)

        assert resp.order_id == "ORDER123"
        assert resp.status == OrderStatus.PENDING
        assert resp.message == "Order modified"

    @pytest.mark.asyncio
    async def test_modify_order_failure(self, adapter):
        await adapter.connect()
        adapter._http.request = AsyncMock(
            return_value=make_response(200, {"status": "error", "message": "Invalid order"})
        )

        resp = await adapter.modify_order("BADORDER", price=100.0)
        assert resp.status == OrderStatus.REJECTED


class TestCancelOrder:
    @pytest.mark.asyncio
    async def test_cancel_order_success(self, adapter):
        await adapter.connect()
        adapter._http.request = AsyncMock(
            return_value=make_response(200, {"status": "success"})
        )
        assert await adapter.cancel_order("ORDER123") is True

    @pytest.mark.asyncio
    async def test_cancel_order_failure(self, adapter):
        await adapter.connect()
        adapter._http.request = AsyncMock(side_effect=Exception("Network error"))
        assert await adapter.cancel_order("ORDER123") is False


# ── Portfolio ────────────────────────────────────────────────────────────


class TestPositions:
    @pytest.mark.asyncio
    async def test_get_positions(self, adapter):
        await adapter.connect()

        data = {
            "status": "success",
            "data": {
                "net": [
                    {
                        "tradingsymbol": "INFY",
                        "instrument_token": "408065",
                        "quantity": 10,
                        "average_price": 1450.0,
                        "last_price": 1500.0,
                    }
                ],
                "day": [],
            },
        }
        adapter._http.request = AsyncMock(return_value=make_response(200, data))

        positions = await adapter.get_positions()

        assert len(positions) == 1
        p = positions[0]
        assert p.symbol == "INFY"
        assert p.quantity == 10
        assert p.side == TradeSide.LONG
        assert p.entry_price == 1450.0

    @pytest.mark.asyncio
    async def test_get_positions_short(self, adapter):
        await adapter.connect()
        data = {
            "status": "success",
            "data": {
                "net": [
                    {"tradingsymbol": "SBIN", "instrument_token": "123", "quantity": -5,
                     "average_price": 500.0, "last_price": 490.0},
                ],
                "day": [],
            },
        }
        adapter._http.request = AsyncMock(return_value=make_response(200, data))

        positions = await adapter.get_positions()
        assert len(positions) == 1
        assert positions[0].side == TradeSide.SHORT
        assert positions[0].quantity == 5

    @pytest.mark.asyncio
    async def test_get_positions_skips_zero_qty(self, adapter):
        await adapter.connect()
        data = {
            "status": "success",
            "data": {"net": [{"tradingsymbol": "X", "quantity": 0}], "day": []},
        }
        adapter._http.request = AsyncMock(return_value=make_response(200, data))
        assert len(await adapter.get_positions()) == 0


class TestHoldings:
    @pytest.mark.asyncio
    async def test_get_holdings(self, adapter):
        await adapter.connect()
        data = {
            "status": "success",
            "data": [
                {
                    "instrument_token": "408065",
                    "tradingsymbol": "INFY",
                    "quantity": 50,
                    "average_price": 1300.0,
                    "last_price": 1500.0,
                }
            ],
        }
        adapter._http.request = AsyncMock(return_value=make_response(200, data))

        holdings = await adapter.get_holdings()
        assert len(holdings) == 1
        assert holdings[0].symbol == "INFY"
        assert holdings[0].quantity == 50


class TestBalance:
    @pytest.mark.asyncio
    async def test_get_account_balance(self, adapter):
        await adapter.connect()
        data = {
            "status": "success",
            "data": {"equity": {"net": 125000.0}},
        }
        adapter._http.request = AsyncMock(return_value=make_response(200, data))

        balance = await adapter.get_account_balance()
        assert balance == 125000.0


class TestOrderBook:
    @pytest.mark.asyncio
    async def test_get_order_book(self, adapter):
        await adapter.connect()
        data = {
            "status": "success",
            "data": [
                {
                    "order_id": "O1",
                    "status": "COMPLETE",
                    "transaction_type": "BUY",
                    "tradingsymbol": "INFY",
                    "quantity": 10,
                    "filled_quantity": 10,
                    "average_price": 1500.0,
                }
            ],
        }
        adapter._http.request = AsyncMock(return_value=make_response(200, data))

        orders = await adapter.get_order_book()
        assert len(orders) == 1
        assert orders[0].order_id == "O1"
        assert orders[0].status == OrderStatus.FILLED


class TestTrades:
    @pytest.mark.asyncio
    async def test_get_trades(self, adapter):
        await adapter.connect()
        data = {
            "status": "success",
            "data": [{"trade_id": "T1", "order_id": "O1", "quantity": 10}],
        }
        adapter._http.request = AsyncMock(return_value=make_response(200, data))

        trades = await adapter.get_trades()
        assert len(trades) == 1
        assert trades[0]["trade_id"] == "T1"
