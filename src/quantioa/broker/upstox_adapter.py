"""
Upstox v2 API adapter — concrete implementation of BrokerAdapter.

Handles:
- Live quote fetching
- Market/Limit order placement
- Position retrieval
- Account balance queries
- Automatic token refresh on 401 responses
"""

from __future__ import annotations

import logging
import time

import httpx

from quantioa.broker.base import BrokerAdapter
from quantioa.broker.token_store import TokenStore
from quantioa.broker.upstox_auth import TokenPair, UpstoxOAuth2
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


class UpstoxAdapter(BrokerAdapter):
    """Upstox v2 API integration.

    Normalizes all Upstox responses to common types so the
    trading engine is broker-agnostic.

    Usage:
        adapter = UpstoxAdapter(user_id="user_123", token_store=store)
        await adapter.connect()
        quote = await adapter.get_quote("NSE_EQ|INE669E01016")  # MON100
        resp = await adapter.place_order(order)
    """

    def __init__(
        self,
        user_id: str,
        token_store: TokenStore,
        auth_client: UpstoxOAuth2 | None = None,
    ) -> None:
        self._user_id = user_id
        self._token_store = token_store
        self._auth_client = auth_client or UpstoxOAuth2()
        self._base_url = settings.upstox_base_url
        self._http = httpx.AsyncClient(timeout=30.0)
        self._token: TokenPair | None = None

    # ── Connection ─────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Load and validate stored token."""
        self._token = await self._token_store.get_valid_token(
            self._user_id, "UPSTOX", self._auth_client
        )
        if self._token is None:
            raise UpstoxConnectionError(
                "No valid Upstox token found. User must authenticate via OAuth2."
            )
        logger.info("Upstox adapter connected for user=%s", self._user_id)

    async def disconnect(self) -> None:
        await self._http.aclose()
        logger.info("Upstox adapter disconnected for user=%s", self._user_id)

    # ── Internal helpers ───────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        if self._token is None:
            raise UpstoxConnectionError("Not connected. Call connect() first.")
        return {
            "Authorization": f"Bearer {self._token.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict:
        """Make an authenticated request with automatic token refresh on 401."""
        url = f"{self._base_url}{path}"
        headers = self._headers()

        resp = await self._http.request(method, url, headers=headers, **kwargs)

        # Auto-refresh on 401
        if resp.status_code == 401:
            logger.info("Got 401, attempting token refresh...")
            await self._refresh_token()
            headers = self._headers()
            resp = await self._http.request(method, url, headers=headers, **kwargs)

        resp.raise_for_status()
        return resp.json()

    async def _refresh_token(self) -> None:
        """Refresh the access token and update store."""
        if self._token is None or not self._token.refresh_token:
            raise UpstoxConnectionError("Cannot refresh: no refresh token available.")

        new_token = await self._auth_client.refresh_access_token(
            self._token.refresh_token
        )
        self._token_store.save(self._user_id, "UPSTOX", new_token)
        self._token = new_token

    # ── Quotes ─────────────────────────────────────────────────────────────

    async def get_quote(self, symbol: str) -> Quote:
        """Get a live quote for a symbol.

        Args:
            symbol: Upstox instrument key (e.g. "NSE_EQ|INE669E01016").
        """
        data = await self._request("GET", f"/market-quote/quotes?instrument_key={symbol}")
        quote_data = data.get("data", {}).get(symbol, {})

        ohlc = quote_data.get("ohlc", {})
        depth = quote_data.get("depth", {})
        best_bid = depth.get("buy", [{}])[0] if depth.get("buy") else {}
        best_ask = depth.get("sell", [{}])[0] if depth.get("sell") else {}

        return Quote(
            symbol=symbol,
            price=float(ohlc.get("close", quote_data.get("last_price", 0))),
            bid=float(best_bid.get("price", 0)),
            ask=float(best_ask.get("price", 0)),
            volume=float(quote_data.get("volume", 0)),
            timestamp=time.time(),
        )

    async def get_order_book_snapshot(self, symbol: str) -> OrderBookSnapshot:
        """Get the order book depth for a symbol."""
        data = await self._request("GET", f"/market-quote/quotes?instrument_key={symbol}")
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
        """Place a buy/sell order via Upstox.

        Maps our common Order type to Upstox API format and normalizes
        the response back to OrderResponse.
        """
        # Map to Upstox transaction type
        transaction_type = "BUY" if order.side == TradeSide.LONG else "SELL"

        payload = {
            "quantity": order.quantity,
            "product": "I",  # Intraday
            "validity": "DAY",
            "price": order.price or 0,
            "tag": "quantioa",
            "instrument_token": order.symbol,
            "order_type": order.order_type.value,
            "transaction_type": transaction_type,
            "disclosed_quantity": 0,
            "trigger_price": 0,
            "is_amo": False,
        }

        try:
            data = await self._request("POST", "/order/place", json=payload)
            order_data = data.get("data", {})

            return OrderResponse(
                order_id=order_data.get("order_id", ""),
                status=OrderStatus.PENDING,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                message=data.get("message", "Order placed"),
                timestamp=time.time(),
            )
        except httpx.HTTPStatusError as e:
            logger.error("Order placement failed: %s", e.response.text)
            return OrderResponse(
                order_id="",
                status=OrderStatus.REJECTED,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                message=f"Order rejected: {e.response.text}",
                timestamp=time.time(),
            )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        try:
            await self._request("DELETE", f"/order/cancel?order_id={order_id}")
            return True
        except Exception as e:
            logger.error("Order cancellation failed: %s", e)
            return False

    # ── Positions & Holdings ───────────────────────────────────────────────

    async def get_positions(self) -> list[Position]:
        """Get all open intraday positions."""
        data = await self._request("GET", "/portfolio/short-term-positions")
        raw_positions = data.get("data", [])

        positions = []
        for p in raw_positions:
            if p.get("quantity", 0) == 0:
                continue

            qty = abs(int(p.get("quantity", 0)))
            side = TradeSide.LONG if int(p.get("quantity", 0)) > 0 else TradeSide.SHORT

            positions.append(
                Position(
                    id=p.get("instrument_token", ""),
                    symbol=p.get("instrument_token", ""),
                    side=side,
                    quantity=qty,
                    entry_price=float(p.get("average_price", 0)),
                    current_price=float(p.get("last_price", 0)),
                    entry_time=time.time(),
                    status=PositionStatus.OPEN,
                )
            )

        return positions

    async def get_holdings(self) -> list[Position]:
        """Get delivery/long-term holdings."""
        data = await self._request("GET", "/portfolio/long-term-holdings")
        raw_holdings = data.get("data", [])

        return [
            Position(
                id=h.get("isin", ""),
                symbol=h.get("instrument_token", h.get("tradingsymbol", "")),
                side=TradeSide.LONG,
                quantity=int(h.get("quantity", 0)),
                entry_price=float(h.get("average_price", 0)),
                current_price=float(h.get("last_price", 0)),
                status=PositionStatus.OPEN,
            )
            for h in raw_holdings
            if int(h.get("quantity", 0)) > 0
        ]

    async def get_account_balance(self) -> float:
        """Get available margin/balance."""
        data = await self._request("GET", "/user/get-funds-and-margin")
        margin_data = data.get("data", {})

        # Upstox has equity and commodity segments
        equity = margin_data.get("equity", {})
        return float(equity.get("available_margin", 0))


class UpstoxConnectionError(Exception):
    """Raised when Upstox adapter cannot connect or authenticate."""
