"""
Upstox WebSocket streaming — market data + portfolio updates.

Provides two independent streaming channels:

1. **Market Data Feed V3** — real-time OHLCV, depth, option greeks
   via Protobuf-encoded WebSocket (MarketDataStreamerV3).

2. **Portfolio Stream Feed** — real-time order status, position changes,
   holding changes via JSON WebSocket.

Both channels support auto-reconnect and callback-based event handling.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Callable

import httpx

from quantioa.broker.upstox_auth import TokenPair
from quantioa.config import settings

logger = logging.getLogger(__name__)

# Type alias for callbacks
Callback = Callable[[dict], None]


def _import_websockets():
    """Lazy import of websockets to avoid hard dependency at import time."""
    try:
        import websockets
        return websockets
    except ImportError:
        raise ImportError(
            "websockets package is required for streaming. "
            "Install it with: pip install websockets"
        )


class MarketDataStream:
    """V3 Market data WebSocket stream.

    Connects to the Upstox Market Data Feed V3 endpoint and delivers
    real-time market data via callbacks.

    Modes:
        - ``ltpc``: Last price + close price only (lightest, 5000 keys max)
        - ``full``: OHLCV + 5-level depth + option greeks (2000 keys max)
        - ``option_greeks``: Option greeks only (3000 keys max)
        - ``full_d30``: 30-level depth (Plus only, 50 keys max)

    Usage::

        stream = MarketDataStream(token)
        stream.on_tick(my_callback)
        stream.on_market_status(my_status_callback)
        await stream.connect()
        await stream.subscribe(["NSE_EQ|INE669E01016"], mode="full")
        # ... later
        await stream.disconnect()
    """

    def __init__(
        self,
        token: TokenPair,
        auto_reconnect: bool = True,
        reconnect_interval: float = 10.0,
        max_retries: int = 5,
    ) -> None:
        self._token = token
        self._auto_reconnect = auto_reconnect
        self._reconnect_interval = reconnect_interval
        self._max_retries = max_retries
        self._ws: Any = None
        self._running = False
        self._tick_callbacks: list[Callback] = []
        self._status_callbacks: list[Callback] = []
        self._listen_task: asyncio.Task | None = None

    def on_tick(self, callback: Callback) -> None:
        """Register a callback for live market data ticks."""
        self._tick_callbacks.append(callback)

    def on_market_status(self, callback: Callback) -> None:
        """Register a callback for market status updates."""
        self._status_callbacks.append(callback)

    async def _get_auth_url(self) -> str:
        """Get the authorized WebSocket redirect URL from the authorize endpoint."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                settings.upstox_ws_market_auth_url,
                headers={
                    "Authorization": f"Bearer {self._token.access_token}",
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["data"]["authorized_redirect_uri"]

    async def connect(self) -> None:
        """Establish the WebSocket connection."""
        ws_mod = _import_websockets()
        wss_url = await self._get_auth_url()
        logger.info("Connecting to Market Data Feed V3...")
        self._ws = await ws_mod.connect(wss_url, ping_interval=30)
        self._running = True
        self._listen_task = asyncio.create_task(self._listen_loop())
        logger.info("Market Data Feed V3 connected")

    async def _listen_loop(self) -> None:
        """Main listen loop with auto-reconnect."""
        retries = 0
        while self._running:
            try:
                async for message in self._ws:
                    retries = 0  # Reset on successful message
                    try:
                        # V3 feed sends JSON messages (after SDK decoding)
                        if isinstance(message, bytes):
                            # Binary protobuf — for now, try JSON decode
                            data = json.loads(message.decode("utf-8"))
                        else:
                            data = json.loads(message)

                        msg_type = data.get("type", "")
                        if msg_type == "market_info":
                            for cb in self._status_callbacks:
                                cb(data)
                        elif msg_type == "live_feed":
                            feeds = data.get("feeds", {})
                            for instrument_key, tick_data in feeds.items():
                                enriched = {
                                    "instrument_key": instrument_key,
                                    **tick_data,
                                }
                                for cb in self._tick_callbacks:
                                    cb(enriched)
                    except (json.JSONDecodeError, UnicodeDecodeError) as e:
                        logger.warning("Failed to decode market message: %s", e)

            except Exception as e:
                ws_mod = _import_websockets()
                if isinstance(e, ws_mod.ConnectionClosedError):
                    logger.warning("Market WS connection closed: %s", e)
                    if not self._auto_reconnect or retries >= self._max_retries:
                        logger.error("Max reconnect retries reached, stopping")
                        self._running = False
                        break
                    retries += 1
                    logger.info(
                        "Reconnecting in %.0fs (attempt %d/%d)...",
                        self._reconnect_interval,
                        retries,
                        self._max_retries,
                    )
                    await asyncio.sleep(self._reconnect_interval)
                    try:
                        wss_url = await self._get_auth_url()
                        self._ws = await ws_mod.connect(wss_url, ping_interval=30)
                    except Exception as re:
                        logger.error("Reconnection failed: %s", re)
                else:
                    logger.error("Market stream error: %s", e)
                    self._running = False
                    break

    async def subscribe(
        self,
        instrument_keys: list[str],
        mode: str = "full",
    ) -> None:
        """Subscribe to market data for given instruments.

        Args:
            instrument_keys: List of instrument keys (e.g. ``["NSE_EQ|INE669E01016"]``)
            mode: One of ``ltpc``, ``full``, ``option_greeks``, ``full_d30``
        """
        if self._ws is None:
            raise RuntimeError("Not connected. Call connect() first.")

        request = {
            "guid": str(uuid.uuid4()).replace("-", ""),
            "method": "sub",
            "data": {
                "mode": mode,
                "instrumentKeys": instrument_keys,
            },
        }
        await self._ws.send(json.dumps(request))
        logger.info("Subscribed to %d instruments in '%s' mode", len(instrument_keys), mode)

    async def unsubscribe(self, instrument_keys: list[str]) -> None:
        """Unsubscribe from market data for given instruments."""
        if self._ws is None:
            return

        request = {
            "guid": str(uuid.uuid4()).replace("-", ""),
            "method": "unsub",
            "data": {
                "instrumentKeys": instrument_keys,
            },
        }
        await self._ws.send(json.dumps(request))
        logger.info("Unsubscribed from %d instruments", len(instrument_keys))

    async def change_mode(
        self,
        instrument_keys: list[str],
        mode: str,
    ) -> None:
        """Change the subscription mode for instruments."""
        if self._ws is None:
            return

        request = {
            "guid": str(uuid.uuid4()).replace("-", ""),
            "method": "change_mode",
            "data": {
                "mode": mode,
                "instrumentKeys": instrument_keys,
            },
        }
        await self._ws.send(json.dumps(request))
        logger.info("Changed mode to '%s' for %d instruments", mode, len(instrument_keys))

    async def disconnect(self) -> None:
        """Disconnect from the WebSocket."""
        self._running = False
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
        if self._ws:
            await self._ws.close()
            self._ws = None
        logger.info("Market Data Feed V3 disconnected")


class PortfolioStream:
    """Portfolio stream feed — real-time order, position, holding updates.

    Uses the Upstox Portfolio Stream Feed endpoint. Supports filtering
    by update type: ``order``, ``gtt_order``, ``position``, ``holding``.

    Usage::

        stream = PortfolioStream(token)
        stream.on_order_update(my_order_callback)
        stream.on_position_update(my_position_callback)
        await stream.connect()
        # ... updates arrive automatically
        await stream.disconnect()
    """

    def __init__(
        self,
        token: TokenPair,
        update_types: list[str] | None = None,
        auto_reconnect: bool = True,
        reconnect_interval: float = 10.0,
        max_retries: int = 5,
    ) -> None:
        self._token = token
        self._update_types = update_types or ["order", "position", "holding"]
        self._auto_reconnect = auto_reconnect
        self._reconnect_interval = reconnect_interval
        self._max_retries = max_retries
        self._ws: Any = None
        self._running = False
        self._order_callbacks: list[Callback] = []
        self._position_callbacks: list[Callback] = []
        self._holding_callbacks: list[Callback] = []
        self._gtt_callbacks: list[Callback] = []
        self._listen_task: asyncio.Task | None = None

    def on_order_update(self, callback: Callback) -> None:
        """Register a callback for order update events."""
        self._order_callbacks.append(callback)

    def on_position_update(self, callback: Callback) -> None:
        """Register a callback for position change events."""
        self._position_callbacks.append(callback)

    def on_holding_update(self, callback: Callback) -> None:
        """Register a callback for holding change events."""
        self._holding_callbacks.append(callback)

    def on_gtt_order_update(self, callback: Callback) -> None:
        """Register a callback for GTT order update events."""
        self._gtt_callbacks.append(callback)

    async def _get_auth_url(self) -> str:
        """Get the authorized WebSocket redirect URL from the authorize endpoint."""
        types_param = "%2C".join(self._update_types)
        url = (
            f"{settings.upstox_base_url}/feed/portfolio-stream-feed/authorize"
            f"?update_types={types_param}"
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self._token.access_token}",
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["data"]["authorized_redirect_uri"]

    async def connect(self) -> None:
        """Establish the portfolio WebSocket connection."""
        ws_mod = _import_websockets()
        wss_url = await self._get_auth_url()
        logger.info(
            "Connecting to Portfolio Stream Feed (types=%s)...",
            self._update_types,
        )
        self._ws = await ws_mod.connect(wss_url, ping_interval=30)
        self._running = True
        self._listen_task = asyncio.create_task(self._listen_loop())
        logger.info("Portfolio Stream Feed connected")

    async def _listen_loop(self) -> None:
        """Main listen loop with auto-reconnect."""
        retries = 0
        while self._running:
            try:
                async for message in self._ws:
                    retries = 0
                    try:
                        if isinstance(message, bytes):
                            data = json.loads(message.decode("utf-8"))
                        else:
                            data = json.loads(message)

                        update_type = data.get("update_type", "")

                        if update_type == "order":
                            for cb in self._order_callbacks:
                                cb(data)
                        elif update_type == "position":
                            for cb in self._position_callbacks:
                                cb(data)
                        elif update_type == "holding":
                            for cb in self._holding_callbacks:
                                cb(data)
                        elif update_type == "gtt_order":
                            for cb in self._gtt_callbacks:
                                cb(data)
                        else:
                            logger.debug("Unknown portfolio update type: %s", update_type)

                    except (json.JSONDecodeError, UnicodeDecodeError) as e:
                        logger.warning("Failed to decode portfolio message: %s", e)

            except Exception as e:
                ws_mod = _import_websockets()
                if isinstance(e, ws_mod.ConnectionClosedError):
                    logger.warning("Portfolio WS connection closed: %s", e)
                    if not self._auto_reconnect or retries >= self._max_retries:
                        logger.error("Max reconnect retries reached, stopping")
                        self._running = False
                        break
                    retries += 1
                    logger.info(
                        "Reconnecting in %.0fs (attempt %d/%d)...",
                        self._reconnect_interval,
                        retries,
                        self._max_retries,
                    )
                    await asyncio.sleep(self._reconnect_interval)
                    try:
                        wss_url = await self._get_auth_url()
                        self._ws = await ws_mod.connect(wss_url, ping_interval=30)
                    except Exception as re:
                        logger.error("Portfolio reconnection failed: %s", re)
                else:
                    logger.error("Portfolio stream error: %s", e)
                    self._running = False
                    break

    async def disconnect(self) -> None:
        """Disconnect from the portfolio WebSocket."""
        self._running = False
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
        if self._ws:
            await self._ws.close()
            self._ws = None
        logger.info("Portfolio Stream Feed disconnected")


class UpstoxStreamer:
    """Unified streaming manager for both market data and portfolio feeds.

    Wraps ``MarketDataStream`` and ``PortfolioStream`` into a single
    convenience class.

    Usage::

        streamer = UpstoxStreamer(token)
        streamer.on_tick(handle_tick)
        streamer.on_order_update(handle_order)
        await streamer.start()
        await streamer.subscribe(["NSE_EQ|INE669E01016"])
        # ...
        await streamer.stop()
    """

    def __init__(
        self,
        token: TokenPair,
        enable_market: bool = True,
        enable_portfolio: bool = True,
        portfolio_update_types: list[str] | None = None,
    ) -> None:
        self._market = (
            MarketDataStream(token) if enable_market else None
        )
        self._portfolio = (
            PortfolioStream(token, update_types=portfolio_update_types)
            if enable_portfolio
            else None
        )

    # ── Callback registration ──────────────────────────────────────────────

    def on_tick(self, callback: Callback) -> None:
        if self._market:
            self._market.on_tick(callback)

    def on_market_status(self, callback: Callback) -> None:
        if self._market:
            self._market.on_market_status(callback)

    def on_order_update(self, callback: Callback) -> None:
        if self._portfolio:
            self._portfolio.on_order_update(callback)

    def on_position_update(self, callback: Callback) -> None:
        if self._portfolio:
            self._portfolio.on_position_update(callback)

    def on_holding_update(self, callback: Callback) -> None:
        if self._portfolio:
            self._portfolio.on_holding_update(callback)

    def on_gtt_order_update(self, callback: Callback) -> None:
        if self._portfolio:
            self._portfolio.on_gtt_order_update(callback)

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Connect both market data and portfolio streams."""
        tasks = []
        if self._market:
            tasks.append(self._market.connect())
        if self._portfolio:
            tasks.append(self._portfolio.connect())
        if tasks:
            await asyncio.gather(*tasks)

    async def stop(self) -> None:
        """Disconnect both streams."""
        tasks = []
        if self._market:
            tasks.append(self._market.disconnect())
        if self._portfolio:
            tasks.append(self._portfolio.disconnect())
        if tasks:
            await asyncio.gather(*tasks)

    # ── Market data controls ───────────────────────────────────────────────

    async def subscribe(
        self,
        instrument_keys: list[str],
        mode: str = "full",
    ) -> None:
        if self._market:
            await self._market.subscribe(instrument_keys, mode)

    async def unsubscribe(self, instrument_keys: list[str]) -> None:
        if self._market:
            await self._market.unsubscribe(instrument_keys)

    async def change_mode(self, instrument_keys: list[str], mode: str) -> None:
        if self._market:
            await self._market.change_mode(instrument_keys, mode)
