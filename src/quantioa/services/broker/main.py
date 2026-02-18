"""
Broker Service — manages broker connections and order routing.

Handles:
- Broker account management (connect/disconnect)
- Live quote fetching
- Order placement, modification, cancellation
- Position and holdings retrieval
- Account balance queries
"""

from __future__ import annotations


from fastapi import FastAPI, Depends, HTTPException, Header
from typing import Annotated

from quantioa.broker.base import BrokerAdapter
from quantioa.broker.factory import get_broker_adapter
from quantioa.broker.token_store import TokenStore
from quantioa.models.enums import BrokerType
from quantioa.models.types import Order

app = FastAPI(title="Quantioa Broker Service", version="0.1.0")

# Dependency
def get_token_store():
    return TokenStore()

async def get_broker(
    broker_type: Annotated[str, Header()],
    user_id: Annotated[str, Header()],
    token_store: TokenStore = Depends(get_token_store)
) -> BrokerAdapter:
    try:
        adapter = get_broker_adapter(user_id, broker_type, token_store)
        await adapter.connect()
        return adapter
    except  ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "broker-service"}


@app.get("/accounts")
async def list_accounts():
    """List connected broker accounts."""
    return {"accounts": [], "message": "Broker accounts — to be implemented"}


@app.get("/quotes/{symbol}")
async def get_quote(
    symbol: str, 
    broker: BrokerAdapter = Depends(get_broker)
):
    """Get live quote for a symbol."""
    quote = await broker.get_quote(symbol)
    return quote


@app.post("/orders")
async def place_order(
    order: Order,
    broker: BrokerAdapter = Depends(get_broker)
):
    """Place a new order."""
    response = await broker.place_order(order)
    return response


@app.get("/positions")
async def get_positions(
    broker: BrokerAdapter = Depends(get_broker)
):
    """Get open positions."""
    positions = await broker.get_positions()
    return {"positions": positions}
