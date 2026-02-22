"""
Async Upstox WebSocket consumer.
"""

import asyncio
import logging
import urllib.parse
from datetime import datetime
import websockets

from quantioa.config import settings
from quantioa.models.types import Tick

logger = logging.getLogger(__name__)


class UpstoxWebSocketClient:
    """Connects to Upstox Market Data Feed."""

    def __init__(self, api_key: str, access_token: str):
        self.api_key = api_key
        self.access_token = access_token
        self.url = settings.upstox_ws_url
        self._ws = None
        self._subscriptions: set[str] = set()
        self._callbacks = []

    def register_callback(self, callback) -> None:
        """Register an async function to receive Ticks."""
        self._callbacks.append(callback)

    def subscribe(self, instrument_keys: list[str]) -> None:
        """Add instruments to the subscription list."""
        self._subscriptions.update(instrument_keys)
        # If already connected, send the subscription message immediately
        if self._ws and self._ws.open:
            asyncio.create_task(self._send_subscription(instrument_keys))

    async def _send_subscription(self, instrument_keys: list[str]) -> None:
        """Send the protobuf/JSON subscription message to Upstox."""
        req = {
            "guid": "quantioa-1",
            "method": "sub",
            "data": {
                "mode": "full",
                "instrumentKeys": list(instrument_keys)
            }
        }
        import json
        await self._ws.send(json.dumps(req))
        logger.info("Subscribed to %d instruments on Upstox WS", len(instrument_keys))

    async def connect_and_listen(self) -> None:
        """Establish connection and listen in an infinite loop."""
        headers = {
            "Api-Version": "2.0",
            "Authorization": f"Bearer {self.access_token}"
        }
        
        while True:
            try:
                logger.info("Connecting to Upstox Market Data WS: %s", self.url)
                async with websockets.connect(self.url, extra_headers=headers) as ws:
                    self._ws = ws
                    logger.info("Successfully connected to Upstox WS.")
                    
                    if self._subscriptions:
                        await self._send_subscription(list(self._subscriptions))

                    async for message in ws:
                        await self._handle_message(message)

            except websockets.exceptions.ConnectionClosed:
                logger.warning("Upstox WS Connection closed. Reconnecting in 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error("Upstox WS Error: %s. Reconnecting in 5s...", e)
                await asyncio.sleep(5)

    async def _handle_message(self, message: bytes | str) -> None:
        """Decode the incoming message and trigger callbacks."""
        import json
        import time
        try:
            # Handle JSON fallback or string messages
            if isinstance(message, str):
                data = json.loads(message)
            else:
                # Upstox v2 feed can be binary Protobuf. For JSON-fallback APIs:
                data = json.loads(message.decode("utf-8"))

            # Expecting normalized data to map to Tick
            # Using data.get to prevent crashes on heartbeats or control messages
            if "symbol" not in data:
                return

            tick = Tick(
                timestamp=data.get("timestamp", time.time()),
                symbol=data["symbol"],
                open=float(data.get("open", 0.0)),
                high=float(data.get("high", 0.0)),
                low=float(data.get("low", 0.0)),
                close=float(data.get("close", 0.0)),
                volume=float(data.get("volume", 0.0))
            )

            # Fire all callbacks concurrently
            tasks = [cb(tick) for cb in self._callbacks]
            if tasks:
                await asyncio.gather(*tasks)

        except Exception as e:
            logger.error("Failed to decode WS message: %s", e)
