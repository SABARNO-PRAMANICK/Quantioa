
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from quantioa.broker.upstox_adapter import UpstoxAdapter
from quantioa.broker.upstox_auth import TokenPair
from quantioa.models.enums import OrderStatus, TradeSide
from quantioa.models.types import Order, OrderType, ProductType, OrderValidity
import httpx

@pytest.fixture
def mock_token_store():
    store = MagicMock()
    # Return a valid token
    store.get_valid_token = AsyncMock(return_value=TokenPair(
        access_token="valid_upstox_token",
        expires_at=20000000000.0, # Far future
        user_id="USER123",
        exchanges=["NSE_EQ"],
        products=["I", "D"]
    ))
    return store

@pytest.fixture
def adapter(mock_token_store):
    return UpstoxAdapter(user_id="USER123", token_store=mock_token_store)

def create_mock_response(status_code, json_data):
    resp = httpx.Response(status_code, json=json_data)
    resp.request = httpx.Request("GET", "https://mock")
    return resp

@pytest.mark.asyncio
async def test_connect(adapter, mock_token_store):
    await adapter.connect()
    assert adapter._token.access_token == "valid_upstox_token"
    mock_token_store.get_valid_token.assert_called_with("USER123", "UPSTOX", adapter._auth_client)

@pytest.mark.asyncio
async def test_get_quote(adapter):
    await adapter.connect()
    
    quote_response = {
        "status": "success",
        "data": {
            "NSE_EQ|INFY": {
                "last_price": 1500.0,
                "volume": 10000,
                "ohlc": {
                    "open": 1490.0,
                    "high": 1510.0,
                    "low": 1490.0,
                    "close": 1495.0
                },
                "depth": {
                    "buy": [{"price": 1499.0, "quantity": 100, "orders": 5}],
                    "sell": [{"price": 1501.0, "quantity": 50, "orders": 2}]
                }
            }
        }
    }

    adapter._http.request = AsyncMock(return_value=create_mock_response(200, quote_response))
    
    quote = await adapter.get_quote("NSE_EQ|INFY")
    
    assert quote.symbol == "NSE_EQ|INFY"
    assert quote.price == 1495.0 # UpstoxAdapter uses ohlc.close if available
    assert quote.bid == 1499.0
    assert quote.ask == 1501.0
    assert quote.volume == 10000

@pytest.mark.asyncio
async def test_place_order(adapter):
    await adapter.connect()
    
    order_response = {
        "status": "success",
        "data": {
            "order_id": "ORDER123"
        },
        "metadata": {
            "latency": 50
        }
    }
    
    order = Order(
        symbol="NSE_EQ|INFY",
        side=TradeSide.LONG,
        quantity=10,
        price=1500.0,
        order_type=OrderType.LIMIT,
        product=ProductType.INTRADAY, 
        validity=OrderValidity.DAY
    )
    
    adapter._http.request = AsyncMock(return_value=create_mock_response(200, order_response))
    
    resp = await adapter.place_order(order)
    
    assert resp.order_id == "ORDER123"
    assert resp.status == OrderStatus.PENDING
    assert resp.latency_ms == 50
    
    # Verify call usage
    args, kwargs = adapter._http.request.call_args
    assert args[0] == "POST"
    assert args[1].endswith("/order/place")
    assert kwargs["json"]["quantity"] == 10
    assert kwargs["json"]["product"] == "I"

@pytest.mark.asyncio
async def test_get_positions(adapter):
    await adapter.connect()
    
    positions_response = {
        "status": "success",
        "data": [
            {
                "instrument_token": "NSE_EQ|INFY",
                "quantity": 10,
                "average_price": 1450.0,
                "last_price": 1500.0,
                "product": "I"
            }
        ]
    }

    adapter._http.request = AsyncMock(return_value=create_mock_response(200, positions_response))
    
    positions = await adapter.get_positions()
    
    assert len(positions) == 1
    p = positions[0]
    assert p.symbol == "NSE_EQ|INFY"
    assert p.quantity == 10
    assert p.side == TradeSide.LONG
    assert p.entry_price == 1450.0
    assert p.current_price == 1500.0
