"""
Zerodha Kite Connect broker adapter.

Handles:
- Order placement and management
- Market data retrieval (Quotes, L1 depth)
- Portfolio and funds management
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from quantioa.broker.base import BrokerAdapter
from quantioa.broker.token_store import TokenStore
from quantioa.broker.types import TokenPair
from quantioa.broker.zerodha_auth import ZerodhaOAuth2
from quantioa.config import settings
from quantioa.models.enums import OrderStatus, OrderType, PositionStatus, TradeSide
from quantioa.models.types import (
    Order,
    OrderBookLevel,
    OrderBookSnapshot,
    OrderResponse,
    Position,
    Quote,
)

logger = logging.getLogger(__name__)

# Zerodha status mapping
_STATUS_MAP: dict[str, OrderStatus] = {
    "COMPLETE": OrderStatus.FILLED,
    "REJECTED": OrderStatus.REJECTED,
    "CANCELLED": OrderStatus.CANCELLED,
    "OPEN": OrderStatus.PENDING,
    "AMO REQ RECEIVED": OrderStatus.PENDING,
    "UPDATE": OrderStatus.PENDING,  # Order modified
    "TRIGGER PENDING": OrderStatus.PENDING,
}


class ZerodhaAdapter(BrokerAdapter):
    """Zerodha Kite Connect API integration."""

    def __init__(
        self,
        user_id: str,
        token_store: TokenStore,
        auth_client: ZerodhaOAuth2 | None = None,
    ) -> None:
        self._user_id = user_id
        self._token_store = token_store
        self._auth_client = auth_client or ZerodhaOAuth2()
        self._base_url = settings.zerodha_base_url
        self._http = httpx.AsyncClient(timeout=30.0)
        self._token: TokenPair | None = None

    async def connect(self) -> None:
        """Load stored token."""
        # Zerodha tokens are valid until 6 AM next day.
        # We rely on TokenStore to provide a valid token.
        # If expired, we CANNOT auto-refresh without user interaction (login flow),
        # as Zerodha does not have a persistent refresh token flow like Upstox (v2).
        self._token = self._token_store.load(self._user_id, "ZERODHA")
        
        if self._token is None:
            raise ZerodhaConnectionError(
                "No Zerodha token found. User must authenticate via OAuth2."
            )
        
        if self._token.is_expired:
             raise ZerodhaConnectionError(
                "Zerodha token expired. User must re-authenticate."
            )

        logger.info("Zerodha adapter connected for user=%s", self._user_id)

    async def disconnect(self) -> None:
        await self._http.aclose()
        logger.info("Zerodha adapter disconnected")

    def _headers(self) -> dict[str, str]:
        if self._token is None:
            raise ZerodhaConnectionError("Not connected")
        return {
            "X-Kite-Version": "3",
            "Authorization": f"token {self._auth_client.api_key}:{self._token.access_token}",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        url = f"{self._base_url}{path}"
        headers = self._headers()
        
        try:
            resp = await self._http.request(method, url, headers=headers, **kwargs)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "error":
                raise ZerodhaAPIError(data.get("message", "Unknown error"))
            return data
        except httpx.HTTPStatusError as e:
            logger.error("Zerodha API error: %s", e.response.text)
            raise ZerodhaAPIError(f"HTTP {e.response.status_code}: {e.response.text}") from e

    # ── Market Data ────────────────────────────────────────────────────────

    async def get_quote(self, symbol: str) -> Quote:
        """Get live quote.
        
        Symbol format: "exchange:symbol" e.g., "NSE:INFY"
        """
        # Zerodha requires 'i' parameter for instruments
        data = await self._request("GET", "/quote", params={"i": symbol})
        quote_data = data.get("data", {}).get(symbol, {})
        
        ohlc = quote_data.get("ohlc", {})
        depth = quote_data.get("depth", {})
        best_bid = depth.get("buy", [{}])[0] if depth.get("buy") else {}
        best_ask = depth.get("sell", [{}])[0] if depth.get("sell") else {}

        return Quote(
            symbol=symbol,
            price=float(quote_data.get("last_price", 0)),
            bid=float(best_bid.get("price", 0)),
            ask=float(best_ask.get("price", 0)),
            volume=float(quote_data.get("volume", 0)),
            timestamp=time.time(),
        )

    async def get_order_book_snapshot(self, symbol: str) -> OrderBookSnapshot:
        data = await self._request("GET", "/quote", params={"i": symbol})
        quote_data = data.get("data", {}).get(symbol, {})
        depth = quote_data.get("depth", {})

        bids = [
            OrderBookLevel(
                price=float(level.get("price", 0)),
                quantity=int(level.get("quantity", 0)),
                orders=int(level.get("orders", 0)),
            )
            for level in depth.get("buy", [])
        ]
        asks = [
            OrderBookLevel(
                price=float(level.get("price", 0)),
                quantity=int(level.get("quantity", 0)),
                orders=int(level.get("orders", 0)),
            )
            for level in depth.get("sell", [])
        ]

        return OrderBookSnapshot(
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=time.time(),
        )

    # ── Orders ─────────────────────────────────────────────────────────────

    async def place_order(self, order: Order) -> OrderResponse:
        transaction_type = "BUY" if order.side == TradeSide.LONG else "SELL"
        
        # Parse symbol to exchange and tradingsymbol
        # Expected format "EXCHANGE:SYMBOL"
        if ":" in order.symbol:
            exchange, tradingsymbol = order.symbol.split(":", 1)
        else:
            # Default fallback or error
            exchange = "NSE"
            tradingsymbol = order.symbol

        # Map ProductType to Zerodha constants
        product_map = {
            "I": "MIS",      # Intraday
            "D": "CNC",      # Delivery
            "MTF": "NRML",   # Margin (Approximate mapping, verify validity)
        }
        product = product_map.get(order.product.value, "MIS") # Default to MIS if unknown

        payload = {
            "exchange": exchange,
            "tradingsymbol": tradingsymbol,
            "transaction_type": transaction_type,
            "quantity": order.quantity,
            "product": product,
            "order_type": order.order_type.value,
            "validity": order.validity.value,
            "price": order.price,
            "trigger_price": order.trigger_price,
            "tag": order.tag,
        }
        
        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}

        try:
            data = await self._request("POST", "/orders/regular", data=payload)
            order_id = data.get("data", {}).get("order_id", "")
            
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.PENDING,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                message="Order placed",
                timestamp=time.time(),
            )
        except ZerodhaAPIError as e:
            return OrderResponse(
                order_id="",
                status=OrderStatus.REJECTED,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                message=str(e),
                timestamp=time.time(),
            )

    async def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        price: float | None = None,
        trigger_price: float | None = None,
        order_type: str | None = None,
    ) -> OrderResponse:
        payload = {}
        if quantity is not None:
            payload["quantity"] = quantity
        if price is not None:
            payload["price"] = price
        if trigger_price is not None:
            payload["trigger_price"] = trigger_price
        if order_type is not None:
            payload["order_type"] = order_type

        try:
            # Zerodha modify endpoint: PUT /orders/regular/:order_id
            await self._request("PUT", f"/orders/regular/{order_id}", data=payload)
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.PENDING,
                symbol="", # Unknown without fetching
                side=TradeSide.LONG, # Unknown
                quantity=quantity or 0,
                message="Order modified",
                timestamp=time.time(),
            )
        except ZerodhaAPIError as e:
             return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                symbol="",
                side=TradeSide.LONG,
                quantity=0,
                message=str(e),
                timestamp=time.time(),
            )

    async def cancel_order(self, order_id: str) -> bool:
        try:
            await self._request("DELETE", f"/orders/regular/{order_id}")
            return True
        except Exception as e:
            logger.error("Cancel order failed: %s", e)
            return False

    async def get_order_status(self, order_id: str) -> OrderResponse:
        orders = await self.get_order_book()
        for o in orders:
            if o.order_id == order_id:
                return o
        raise ZerodhaAPIError(f"Order {order_id} not found")

    async def get_order_book(self) -> list[OrderResponse]:
        data = await self._request("GET", "/orders")
        raw_orders = data.get("data", [])
        return [self._parse_order(o) for o in raw_orders]

    async def get_trades(self) -> list[dict]:
        data = await self._request("GET", "/trades")
        return data.get("data", [])

    # ── Portfolio ──────────────────────────────────────────────────────────

    async def get_positions(self) -> list[Position]:
        data = await self._request("GET", "/portfolio/positions")
        # Zerodha returns net and day positions. We usually care about net for overall or day for intraday?
        # Let's combine or just take net. 'net' usually implies open positions.
        
        # For simplicity, let's look at 'net' which gives current open positions across intervals
        net_positions = data.get("data", {}).get("net", [])
        
        positions = []
        for p in net_positions:
            qty = int(p.get("quantity", 0))
            if qty == 0:
                continue
                
            side = TradeSide.LONG if qty > 0 else TradeSide.SHORT
            
            positions.append(
                Position(
                    id=p.get("instrument_token", ""),
                    symbol=p.get("tradingsymbol", ""),
                    side=side,
                    quantity=abs(qty),
                    entry_price=float(p.get("average_price", 0)),
                    current_price=float(p.get("last_price", 0)),
                    entry_time=time.time(), # Not provided by API
                    status=PositionStatus.OPEN,
                )
            )
        return positions

    async def get_holdings(self) -> list[Position]:
        data = await self._request("GET", "/portfolio/holdings")
        raw_holdings = data.get("data", [])
        
        return [
            Position(
                id=str(h.get("instrument_token", "")),
                symbol=h.get("tradingsymbol", ""),
                side=TradeSide.LONG,
                quantity=int(h.get("quantity", 0)),
                entry_price=float(h.get("average_price", 0)),
                current_price=float(h.get("last_price", 0)),
                status=PositionStatus.OPEN,
            )
            for h in raw_holdings
        ]

    async def get_account_balance(self) -> float:
        data = await self._request("GET", "/user/margins")
        equity = data.get("data", {}).get("equity", {})
        return float(equity.get("net", 0)) # Net cash balance

    # ── Helpers ────────────────────────────────────────────────────────────

    def _parse_order(self, data: dict) -> OrderResponse:
        status = _STATUS_MAP.get(data.get("status", ""), OrderStatus.PENDING)
        transaction_type = data.get("transaction_type", "BUY")
        side = TradeSide.LONG if transaction_type == "BUY" else TradeSide.SHORT
        
        return OrderResponse(
            order_id=data.get("order_id", ""),
            status=status,
            symbol=data.get("tradingsymbol", ""),
            side=side,
            quantity=int(data.get("quantity", 0)),
            filled_quantity=int(data.get("filled_quantity", 0)),
            filled_price=float(data.get("average_price", 0)) if status == OrderStatus.FILLED else None,
            message=data.get("status_message", ""),
            timestamp=time.time(), # ideally parse order_timestamp
            exchange_order_id=data.get("exchange_order_id", ""),
            average_price=float(data.get("average_price", 0)),
        )


class ZerodhaConnectionError(Exception):
    """Raised when connection fails."""

class ZerodhaAPIError(Exception):
    """Raised when API returns error."""
