
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from quantioa.broker.zerodha_adapter import ZerodhaAdapter
from quantioa.broker.types import TokenPair
from quantioa.models.enums import OrderStatus, TradeSide
from quantioa.models.types import Order, OrderType, ProductType, OrderValidity
import httpx

@pytest.fixture
def mock_token_store():
    store = MagicMock()
    # Return a valid token
    store.load.return_value = TokenPair(
        access_token="valid_token",
        expires_at=20000000000.0, # Far future
        user_id="USER123",
        exchanges=["NSE"],
        products=["CNC"]
    )
    return store

@pytest.fixture
def adapter(mock_token_store):
    return ZerodhaAdapter(user_id="USER123", token_store=mock_token_store)

@pytest.mark.asyncio
async def test_connect(adapter, mock_token_store):
    await adapter.connect()
    assert adapter._token.access_token == "valid_token"
    mock_token_store.load.assert_called_with("USER123", "ZERODHA")

def create_mock_response(status_code, json_data):
    resp = httpx.Response(status_code, json=json_data)
    resp.request = httpx.Request("GET", "https://mock")
    return resp

@pytest.mark.asyncio
async def test_get_quote(adapter):
    await adapter.connect()
    
    quote_response = {
        "status": "success",
        "data": {
            "NSE:INFY": {
                "instrument_token": 408065,
                "timestamp": "2021-01-01 10:00:00",
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

    # Mock the http client request method
    adapter._http.request = AsyncMock(return_value=create_mock_response(200, quote_response))
    
    quote = await adapter.get_quote("NSE:INFY")
    
    assert quote.symbol == "NSE:INFY"
    assert quote.price == 1500.0
    assert quote.bid == 1499.0
    assert quote.ask == 1501.0
    assert quote.volume == 10000
    
    # Verify request call
    adapter._http.request.assert_called_with(
        "GET", 
        "https://api.kite.trade/quote", 
        headers={'X-Kite-Version': '3', 'Authorization': 'token :valid_token'}, 
        params={'i': 'NSE:INFY'}
    )

@pytest.mark.asyncio
async def test_place_order(adapter):
    await adapter.connect()
    
    order_response = {
        "status": "success",
        "data": {
            "order_id": "ORDER123"
        }
    }
    
    order = Order(
        symbol="NSE:INFY",
        side=TradeSide.LONG,
        quantity=10,
        price=1500.0,
        order_type=OrderType.LIMIT,
        product=ProductType.DELIVERY, # Maps to "D" -> "CNC"
        validity=OrderValidity.DAY
    )
    
    adapter._http.request = AsyncMock(return_value=create_mock_response(200, order_response))
    
    resp = await adapter.place_order(order)
    
    assert resp.order_id == "ORDER123"
    assert resp.status == OrderStatus.PENDING
    
    adapter._http.request.assert_called_with(
        "POST",
        "https://api.kite.trade/orders/regular",
        headers={'X-Kite-Version': '3', 'Authorization': 'token :valid_token'},
        data={
            'exchange': 'NSE',
            'tradingsymbol': 'INFY',
            'transaction_type': 'BUY',
            'quantity': 10,
            'product': 'CNC', # Expect mapped value
            'order_type': 'LIMIT',
            'validity': 'DAY',
            'price': 1500.0,
            'trigger_price': 0.0,
            'tag': 'quantioa'
        }
    )

@pytest.mark.asyncio
async def test_get_positions(adapter):
    await adapter.connect()
    
    positions_response = {
        "status": "success",
        "data": {
            "net": [
                {
                    "tradingsymbol": "INFY",
                    "exchange": "NSE",
                    "instrument_token": "408065",
                    "product": "CNC",
                    "quantity": 10,
                    "overnight_quantity": 0,
                    "multiplier": 1,
                    "average_price": 1450.0,
                    "close_price": 1490.0,
                    "last_price": 1500.0,
                    "value": -14500.0,
                    "pnl": 500.0,
                    "m2m": 500.0,
                    "unrealised": 500.0,
                    "realised": 0.0,
                    "buy_quantity": 10,
                    "buy_price": 1450.0,
                    "buy_value": 14500.0,
                    "sell_quantity": 0,
                    "sell_price": 0.0,
                    "sell_value": 0.0,
                    "day_buy_quantity": 10,
                    "day_buy_price": 1450.0,
                    "day_buy_value": 14500.0,
                    "day_sell_quantity": 0,
                    "day_sell_price": 0.0,
                    "day_sell_value": 0.0
                }
            ],
            "day": []
        }
    }

    adapter._http.request = AsyncMock(return_value=create_mock_response(200, positions_response))
    
    positions = await adapter.get_positions()
    
    assert len(positions) == 1
    p = positions[0]
    assert p.symbol == "INFY"
    assert p.quantity == 10
    assert p.side == TradeSide.LONG
    assert p.entry_price == 1450.0
    assert p.current_price == 1500.0
