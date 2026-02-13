"""
Upstox v3 API adapter — concrete implementation of BrokerAdapter.

Handles:
- V3 order placement/modification/cancellation (HFT endpoint)
- Multi-order batch operations
- Live quote fetching & order book depth
- Position/holdings/balance retrieval
- Trade history & P&L reports
- Automatic token refresh on 401 responses
- Latency tracking from V3 metadata
"""

from __future__ import annotations

import logging
import time
from typing import Any

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

# ── Upstox order status → internal OrderStatus mapping ──────────────────────

_STATUS_MAP: dict[str, OrderStatus] = {
    "put order req received": OrderStatus.PENDING,
    "validation pending": OrderStatus.PENDING,
    "open pending": OrderStatus.PENDING,
    "open": OrderStatus.PENDING,
    "trigger pending": OrderStatus.PENDING,
    "modify pending": OrderStatus.PENDING,
    "modify validation pending": OrderStatus.PENDING,
    "cancel pending": OrderStatus.PENDING,
    "after market order req received": OrderStatus.PENDING,
    "modify after market order req received": OrderStatus.PENDING,
    "complete": OrderStatus.FILLED,
    "modified": OrderStatus.PENDING,
    "cancelled": OrderStatus.CANCELLED,
    "cancelled after market order": OrderStatus.CANCELLED,
    "rejected": OrderStatus.REJECTED,
    "not cancelled": OrderStatus.PENDING,
    "not modified": OrderStatus.PENDING,
}


def _map_status(raw: str) -> OrderStatus:
    """Map Upstox order status string to internal OrderStatus enum."""
    return _STATUS_MAP.get(raw.lower().strip(), OrderStatus.PENDING)


class UpstoxAdapter(BrokerAdapter):
    """Upstox v3 API integration.

    Normalizes all Upstox responses to common types so the
    trading engine is broker-agnostic.

    Usage::

        adapter = UpstoxAdapter(user_id="user_123", token_store=store)
        await adapter.connect()
        quote = await adapter.get_quote("NSE_EQ|INE669E01016")
        resp = await adapter.place_order(order)
        await adapter.modify_order(resp.order_id, price=105.0)
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
        self._base_url = settings.upstox_base_url  # v2 for queries
        self._hft_url = settings.upstox_hft_base_url  # v3 for orders
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
        logger.info(
            "Upstox adapter connected for user=%s (exchanges=%s)",
            self._user_id,
            self._token.exchanges,
        )

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
        *,
        base_url: str | None = None,
        **kwargs: Any,
    ) -> dict:
        """Make an authenticated request with automatic token refresh on 401.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: API path (e.g. ``/order/place``).
            base_url: Override the base URL (default: v2 for queries).
            **kwargs: Passed to ``httpx.request``.
        """
        url = f"{base_url or self._base_url}{path}"
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
            symbol: Upstox instrument key (e.g. ``"NSE_EQ|INE669E01016"``).
        """
        data = await self._request(
            "GET", f"/market-quote/quotes?instrument_key={symbol}"
        )
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
        data = await self._request(
            "GET", f"/market-quote/quotes?instrument_key={symbol}"
        )
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

    # ── V3 Order Operations ────────────────────────────────────────────────

    async def place_order(self, order: Order) -> OrderResponse:
        """Place a buy/sell order via Upstox V3 API.

        Uses the HFT endpoint (``api-hft.upstox.com/v3``) for lowest
        latency. Supports auto-slicing for large orders.
        """
        transaction_type = "BUY" if order.side == TradeSide.LONG else "SELL"

        payload: dict[str, Any] = {
            "quantity": order.quantity,
            "product": order.product.value,
            "validity": order.validity.value,
            "price": order.price or 0,
            "tag": order.tag,
            "instrument_token": order.symbol,
            "order_type": order.order_type.value,
            "transaction_type": transaction_type,
            "disclosed_quantity": 0,
            "trigger_price": order.trigger_price,
            "is_amo": order.is_amo,
        }

        # Auto-slicing for large orders
        if order.slice:
            payload["slice"] = True

        try:
            data = await self._request(
                "POST", "/order/place", base_url=self._hft_url, json=payload
            )
            order_data = data.get("data", {})
            metadata = data.get("metadata", {})

            latency = int(metadata.get("latency", 0))
            if latency > 0:
                logger.debug("V3 order latency: %d ms", latency)

            return OrderResponse(
                order_id=order_data.get("order_id", ""),
                status=OrderStatus.PENDING,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                message=data.get("message", "Order placed"),
                timestamp=time.time(),
                latency_ms=latency,
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

    async def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        price: float | None = None,
        trigger_price: float | None = None,
        order_type: str | None = None,
    ) -> OrderResponse:
        """Modify a pending order via Upstox V3 API.

        Only the fields provided will be modified; others remain unchanged.
        """
        payload: dict[str, Any] = {"order_id": order_id}

        if quantity is not None:
            payload["quantity"] = quantity
        if price is not None:
            payload["price"] = price
        if trigger_price is not None:
            payload["trigger_price"] = trigger_price
        if order_type is not None:
            payload["order_type"] = order_type

        try:
            data = await self._request(
                "PUT", "/order/modify", base_url=self._hft_url, json=payload
            )
            order_data = data.get("data", {})
            metadata = data.get("metadata", {})

            return OrderResponse(
                order_id=order_data.get("order_id", order_id),
                status=OrderStatus.PENDING,
                symbol=order_data.get("instrument_token", ""),
                side=TradeSide.LONG,  # Will be updated when we fetch status
                quantity=quantity or 0,
                message=data.get("message", "Order modified"),
                timestamp=time.time(),
                latency_ms=int(metadata.get("latency", 0)),
            )
        except httpx.HTTPStatusError as e:
            logger.error("Order modification failed: %s", e.response.text)
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                symbol="",
                side=TradeSide.LONG,
                quantity=0,
                message=f"Modification failed: {e.response.text}",
                timestamp=time.time(),
            )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order via Upstox V3 API."""
        try:
            await self._request(
                "DELETE",
                f"/order/cancel?order_id={order_id}",
                base_url=self._hft_url,
            )
            return True
        except Exception as e:
            logger.error("Order cancellation failed: %s", e)
            return False

    # ── Multi-Order Operations ─────────────────────────────────────────────

    async def place_multi_order(self, orders: list[Order]) -> list[OrderResponse]:
        """Place multiple orders in a single batch (max 25).

        Uses ``POST /v2/order/multi/place``.
        """
        if len(orders) > 25:
            raise ValueError("Upstox multi-order API supports max 25 orders per batch")

        payloads = []
        for order in orders:
            transaction_type = "BUY" if order.side == TradeSide.LONG else "SELL"
            payloads.append({
                "quantity": order.quantity,
                "product": order.product.value,
                "validity": order.validity.value,
                "price": order.price or 0,
                "tag": order.tag,
                "instrument_token": order.symbol,
                "order_type": order.order_type.value,
                "transaction_type": transaction_type,
                "disclosed_quantity": 0,
                "trigger_price": order.trigger_price,
                "is_amo": order.is_amo,
                "correlation_id": f"multi_{int(time.time())}_{i}",
                "slice": order.slice,
            })

        try:
            data = await self._request(
                "POST", "/order/multi/place", json=payloads
            )
            results = data.get("data", [])

            responses = []
            for i, result in enumerate(results):
                responses.append(OrderResponse(
                    order_id=result.get("order_id", ""),
                    status=(
                        OrderStatus.PENDING
                        if result.get("status") == "success"
                        else OrderStatus.REJECTED
                    ),
                    symbol=orders[i].symbol if i < len(orders) else "",
                    side=orders[i].side if i < len(orders) else TradeSide.LONG,
                    quantity=orders[i].quantity if i < len(orders) else 0,
                    message=result.get("message", ""),
                    timestamp=time.time(),
                ))
            return responses

        except httpx.HTTPStatusError as e:
            logger.error("Multi-order placement failed: %s", e.response.text)
            return [
                OrderResponse(
                    order_id="",
                    status=OrderStatus.REJECTED,
                    symbol=o.symbol,
                    side=o.side,
                    quantity=o.quantity,
                    message=f"Multi-order failed: {e.response.text}",
                    timestamp=time.time(),
                )
                for o in orders
            ]

    async def cancel_all_orders(
        self,
        segment: str | None = None,
        tag: str | None = None,
    ) -> bool:
        """Cancel multiple orders filtered by segment and/or tag.

        Uses ``DELETE /v2/order/multi/cancel``.
        """
        params: dict[str, str] = {}
        if segment:
            params["segment"] = segment
        if tag:
            params["tag"] = tag

        try:
            await self._request("DELETE", "/order/multi/cancel", params=params)
            return True
        except Exception as e:
            logger.error("Multi-cancel failed: %s", e)
            return False

    async def exit_all_positions(self) -> bool:
        """Exit all open positions.

        Uses ``POST /v2/order/positions/exit``.
        """
        try:
            await self._request("POST", "/order/positions/exit")
            logger.info("All positions exit request sent")
            return True
        except Exception as e:
            logger.error("Exit all positions failed: %s", e)
            return False

    # ── Order Queries ──────────────────────────────────────────────────────

    async def get_order_status(self, order_id: str) -> OrderResponse:
        """Get current status/details of a specific order."""
        data = await self._request(
            "GET", f"/order/details?order_id={order_id}"
        )
        order_data = data.get("data", {})
        return self._parse_order_response(order_data)

    async def get_order_history(self, order_id: str) -> list[dict]:
        """Get full status history for an order.

        Returns a list of status change events.
        """
        data = await self._request(
            "GET", f"/order/history?order_id={order_id}"
        )
        return data.get("data", [])

    async def get_order_book(self) -> list[OrderResponse]:
        """Get all orders placed today."""
        data = await self._request("GET", "/order/retrieve-all")
        raw_orders = data.get("data", [])
        return [self._parse_order_response(o) for o in raw_orders]

    async def get_trades(self) -> list[dict]:
        """Get all trades executed today."""
        data = await self._request("GET", "/order/trades/get-trades-for-day")
        return data.get("data", [])

    async def get_order_trades(self, order_id: str) -> list[dict]:
        """Get trades for a specific order."""
        data = await self._request(
            "GET", f"/order/trades?order_id={order_id}"
        )
        return data.get("data", [])

    async def get_trade_history(
        self,
        segment: str,
        start_date: str,
        end_date: str,
        page_number: int = 1,
        page_size: int = 500,
    ) -> list[dict]:
        """Get historical trades with brokerage charges.

        Uses ``GET /v2/charges/historical-trades``.

        Args:
            segment: EQ, FO, COM, CD
            start_date: dd-mm-yyyy format
            end_date: dd-mm-yyyy format
        """
        data = await self._request(
            "GET",
            "/charges/historical-trades",
            params={
                "segment": segment,
                "start_date": start_date,
                "end_date": end_date,
                "page_number": page_number,
                "page_size": page_size,
            },
        )
        return data.get("data", [])

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

    # ── P&L & Charges ──────────────────────────────────────────────────────

    async def get_pnl_report_meta(
        self,
        segment: str,
        financial_year: str,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict:
        """Get P&L report metadata (total trade count, page size limit).

        Args:
            segment: EQ, FO, COM, CD
            financial_year: e.g. "2324" for FY 2023-24
            from_date: dd-mm-yyyy (optional, within the FY)
            to_date: dd-mm-yyyy (optional, within the FY)
        """
        params: dict[str, str] = {
            "segment": segment,
            "financial_year": financial_year,
        }
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date

        data = await self._request(
            "GET", "/trade/profit-loss/metadata", params=params
        )
        return data.get("data", {})

    async def get_pnl_report(
        self,
        segment: str,
        financial_year: str,
        page_number: int = 1,
        page_size: int = 500,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict]:
        """Get trade-wise P&L report.

        Args:
            segment: EQ, FO, COM, CD
            financial_year: e.g. "2324" for FY 2023-24
            page_number: 1-indexed page number
            page_size: max from metadata API
        """
        params: dict[str, Any] = {
            "segment": segment,
            "financial_year": financial_year,
            "page_number": page_number,
            "page_size": page_size,
        }
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date

        data = await self._request(
            "GET", "/trade/profit-loss/data", params=params
        )
        return data.get("data", [])

    async def get_trade_charges(
        self,
        segment: str,
        financial_year: str,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict:
        """Get trade charges breakdown (brokerage, GST, STT, stamp duty).

        Args:
            segment: EQ, FO, COM, CD
            financial_year: e.g. "2324" for FY 2023-24
        """
        params: dict[str, str] = {
            "segment": segment,
            "financial_year": financial_year,
        }
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date

        data = await self._request(
            "GET", "/trade/profit-loss/charges", params=params
        )
        return data.get("data", {})

    # ── Internal Parsers ───────────────────────────────────────────────────

    def _parse_order_response(self, data: dict) -> OrderResponse:
        """Convert a raw Upstox order dict to our OrderResponse."""
        transaction_type = data.get("transaction_type", "BUY")
        side = TradeSide.LONG if transaction_type == "BUY" else TradeSide.SHORT

        raw_status = data.get("status", "")
        status = _map_status(raw_status)

        # Partially filled detection
        filled_qty = int(data.get("filled_quantity", 0))
        total_qty = int(data.get("quantity", 0))
        if 0 < filled_qty < total_qty and status == OrderStatus.PENDING:
            status = OrderStatus.PARTIALLY_FILLED

        return OrderResponse(
            order_id=data.get("order_id", ""),
            status=status,
            symbol=data.get("instrument_token", data.get("instrument_key", "")),
            side=side,
            quantity=total_qty,
            filled_price=float(data.get("average_price", 0)) or None,
            filled_quantity=filled_qty,
            message=data.get("status_message", ""),
            timestamp=time.time(),
            exchange_order_id=data.get("exchange_order_id", ""),
            average_price=float(data.get("average_price", 0)),
        )


class UpstoxConnectionError(Exception):
    """Raised when Upstox adapter cannot connect or authenticate."""
