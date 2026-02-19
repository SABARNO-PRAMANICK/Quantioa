"""
Unit tests for the Upstox v3 broker adapter.

Tests: connect, get_quote, place_order, modify_order, cancel_order,
       get_positions, get_holdings, get_account_balance, 401 auto-refresh.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import httpx

from quantioa.broker.upstox_adapter import UpstoxAdapter
from quantioa.broker.types import TokenPair
from quantioa.models.enums import OrderStatus, OrderType, TradeSide, ProductType, OrderValidity
from quantioa.models.types import Order


@pytest.fixture
def mock_token_store():
    store = MagicMock()
    store.get_valid_token = AsyncMock(return_value=TokenPair(
        access_token="valid_upstox_token",
        expires_at=20000000000.0,
        user_id="USER123",
        exchanges=["NSE_EQ"],
        products=["I", "D"],
    ))
    return store


@pytest.fixture
def adapter(mock_token_store):
    return UpstoxAdapter(user_id="USER123", token_store=mock_token_store)


def make_response(status_code, json_data):
    resp = httpx.Response(status_code, json=json_data)
    resp.request = httpx.Request("GET", "https://mock")
    return resp


# ── Connect ──────────────────────────────────────────────────────────────


class TestConnect:
    @pytest.mark.asyncio
    async def test_connect_loads_token(self, adapter, mock_token_store):
        await adapter.connect()
        assert adapter._token.access_token == "valid_upstox_token"
        mock_token_store.get_valid_token.assert_called_with(
            "USER123", "UPSTOX", adapter._auth_client
        )

    @pytest.mark.asyncio
    async def test_connect_no_token_raises(self, mock_token_store):
        mock_token_store.get_valid_token = AsyncMock(return_value=None)
        adapter = UpstoxAdapter(user_id="USER123", token_store=mock_token_store)
        with pytest.raises(Exception, match="No valid Upstox token"):
            await adapter.connect()


# ── Quotes ───────────────────────────────────────────────────────────────


class TestGetQuote:
    @pytest.mark.asyncio
    async def test_get_quote(self, adapter):
        await adapter.connect()

        quote_response = {
            "status": "success",
            "data": {
                "NSE_EQ|INFY": {
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

        quote = await adapter.get_quote("NSE_EQ|INFY")

        assert quote.symbol == "NSE_EQ|INFY"
        assert quote.price == 1495.0
        assert quote.bid == 1499.0
        assert quote.ask == 1501.0
        assert quote.volume == 10000

    @pytest.mark.asyncio
    async def test_get_quote_no_depth(self, adapter):
        """Quote should handle missing order book depth gracefully."""
        await adapter.connect()

        quote_response = {
            "status": "success",
            "data": {
                "NSE_EQ|INFY": {
                    "last_price": 1500.0,
                    "volume": 5000,
                    "ohlc": {"close": 1500.0},
                    "depth": {},
                }
            },
        }
        adapter._http.request = AsyncMock(return_value=make_response(200, quote_response))

        quote = await adapter.get_quote("NSE_EQ|INFY")
        assert quote.bid == 0
        assert quote.ask == 0


# ── Orders ───────────────────────────────────────────────────────────────


class TestPlaceOrder:
    @pytest.mark.asyncio
    async def test_place_order_success(self, adapter):
        await adapter.connect()

        order_response = {
            "status": "success",
            "data": {"order_id": "ORDER123"},
            "metadata": {"latency": 50},
        }

        order = Order(
            symbol="NSE_EQ|INFY",
            side=TradeSide.LONG,
            quantity=10,
            price=1500.0,
            order_type=OrderType.LIMIT,
            product=ProductType.INTRADAY,
            validity=OrderValidity.DAY,
        )

        adapter._http.request = AsyncMock(return_value=make_response(200, order_response))

        resp = await adapter.place_order(order)

        assert resp.order_id == "ORDER123"
        assert resp.status == OrderStatus.PENDING
        assert resp.latency_ms == 50

        args, kwargs = adapter._http.request.call_args
        assert args[0] == "POST"
        assert args[1].endswith("/order/place")
        assert kwargs["json"]["quantity"] == 10
        assert kwargs["json"]["product"] == "I"

    @pytest.mark.asyncio
    async def test_place_order_rejected(self, adapter):
        """HTTP error should return REJECTED status, not raise."""
        await adapter.connect()

        error_resp = make_response(400, {"error": "Insufficient margin"})
        adapter._http.request = AsyncMock(side_effect=httpx.HTTPStatusError(
            "400", request=error_resp.request, response=error_resp
        ))

        order = Order(symbol="NSE_EQ|INFY", side=TradeSide.LONG, quantity=10)
        resp = await adapter.place_order(order)

        assert resp.status == OrderStatus.REJECTED


class TestModifyOrder:
    @pytest.mark.asyncio
    async def test_modify_order_success(self, adapter):
        await adapter.connect()

        modify_response = {
            "status": "success",
            "data": {"order_id": "ORDER123"},
            "metadata": {"latency": 30},
        }
        adapter._http.request = AsyncMock(return_value=make_response(200, modify_response))

        resp = await adapter.modify_order("ORDER123", price=1510.0)

        assert resp.order_id == "ORDER123"
        assert resp.status == OrderStatus.PENDING

    @pytest.mark.asyncio
    async def test_modify_order_failure(self, adapter):
        await adapter.connect()

        error_resp = make_response(400, {"error": "Order not found"})
        adapter._http.request = AsyncMock(side_effect=httpx.HTTPStatusError(
            "400", request=error_resp.request, response=error_resp
        ))

        resp = await adapter.modify_order("BADORDER", price=100.0)
        assert resp.status == OrderStatus.REJECTED


class TestCancelOrder:
    @pytest.mark.asyncio
    async def test_cancel_order_success(self, adapter):
        await adapter.connect()
        adapter._http.request = AsyncMock(
            return_value=make_response(200, {"status": "success"})
        )
        result = await adapter.cancel_order("ORDER123")
        assert result is True

    @pytest.mark.asyncio
    async def test_cancel_order_failure(self, adapter):
        await adapter.connect()
        adapter._http.request = AsyncMock(side_effect=Exception("Network error"))
        result = await adapter.cancel_order("ORDER123")
        assert result is False


# ── Portfolio ────────────────────────────────────────────────────────────


class TestPositions:
    @pytest.mark.asyncio
    async def test_get_positions(self, adapter):
        await adapter.connect()

        positions_response = {
            "status": "success",
            "data": [
                {
                    "instrument_token": "NSE_EQ|INFY",
                    "quantity": 10,
                    "average_price": 1450.0,
                    "last_price": 1500.0,
                    "product": "I",
                }
            ],
        }
        adapter._http.request = AsyncMock(
            return_value=make_response(200, positions_response)
        )

        positions = await adapter.get_positions()

        assert len(positions) == 1
        p = positions[0]
        assert p.symbol == "NSE_EQ|INFY"
        assert p.quantity == 10
        assert p.side == TradeSide.LONG
        assert p.entry_price == 1450.0
        assert p.current_price == 1500.0

    @pytest.mark.asyncio
    async def test_get_positions_skips_zero_qty(self, adapter):
        await adapter.connect()
        positions_response = {
            "status": "success",
            "data": [
                {"instrument_token": "NSE_EQ|INFY", "quantity": 0, "average_price": 100.0},
            ],
        }
        adapter._http.request = AsyncMock(
            return_value=make_response(200, positions_response)
        )
        positions = await adapter.get_positions()
        assert len(positions) == 0


class TestHoldings:
    @pytest.mark.asyncio
    async def test_get_holdings(self, adapter):
        await adapter.connect()

        holdings_response = {
            "status": "success",
            "data": [
                {
                    "isin": "INE009A01021",
                    "instrument_token": "NSE_EQ|INFY",
                    "quantity": 50,
                    "average_price": 1300.0,
                    "last_price": 1500.0,
                }
            ],
        }
        adapter._http.request = AsyncMock(
            return_value=make_response(200, holdings_response)
        )

        holdings = await adapter.get_holdings()

        assert len(holdings) == 1
        h = holdings[0]
        assert h.id == "INE009A01021"
        assert h.quantity == 50
        assert h.side == TradeSide.LONG


class TestBalance:
    @pytest.mark.asyncio
    async def test_get_account_balance(self, adapter):
        await adapter.connect()

        balance_response = {
            "status": "success",
            "data": {"equity": {"available_margin": 75000.0}},
        }
        adapter._http.request = AsyncMock(
            return_value=make_response(200, balance_response)
        )

        balance = await adapter.get_account_balance()
        assert balance == 75000.0


# ── Auto-Refresh on 401 ─────────────────────────────────────────────────


class TestAutoRefresh:
    @pytest.mark.asyncio
    async def test_401_triggers_token_refresh(self, adapter, mock_token_store):
        await adapter.connect()

        # Ensure the connected token has a refresh_token
        adapter._token = TokenPair(
            access_token="old_token",
            expires_at=20000000000.0,
            refresh_token="old_refresh_token",
        )

        # First call returns 401, second succeeds
        resp_401 = make_response(401, {"error": "Unauthorized"})
        resp_200 = make_response(200, {
            "status": "success",
            "data": {"equity": {"available_margin": 50000.0}},
        })
        adapter._http.request = AsyncMock(side_effect=[resp_401, resp_200])

        # Mock the auth client refresh
        new_token = TokenPair(access_token="refreshed_token", expires_at=20000000000.0)
        adapter._auth_client.refresh_access_token = AsyncMock(return_value=new_token)

        balance = await adapter.get_account_balance()
        assert balance == 50000.0
        adapter._auth_client.refresh_access_token.assert_called_once()

