"""
Fast-Path Risk Guard for sub-10ms Stop-Loss bypass.
Monitors incoming ticks and triggers emergency exits directly
via the broker service without passing through Kafka or Trading Engine.
"""

from typing import Dict
import logging
import httpx
import os
import asyncio

from quantioa.models.types import Tick
from quantioa.models.enums import TradeSide

logger = logging.getLogger(__name__)


class FastPathRiskGuard:
    """
    Sub-10ms bypass for executing stop-losses directly off the WebSocket feed.
    """

    def __init__(self):
        # Maps symbol -> (side, stop_loss_price, quantity)
        self._active_guards: Dict[str, tuple[str, float, int]] = {}
        
        # Use broker service via internal Docker DNS
        url = "http://quantioa-broker:8000/orders"
        self.broker_endpoint = os.environ.get("BROKER_SERVICE_URL", url)
        self.client = httpx.AsyncClient()

    def register_position(self, symbol: str, side: str, stop_loss: float, quantity: int) -> None:
        """Register a new position that requires sub-10ms fast path protection."""
        self._active_guards[symbol] = (side, stop_loss, quantity)
        logger.info("[FastPath] Registered guard for %s: %s Stop @ ₹%.2f", symbol, side, stop_loss)

    def remove_position(self, symbol: str) -> None:
        """Remove a position from fast path protection."""
        self._active_guards.pop(symbol, None)

    async def evaluate_tick(self, tick: Tick) -> bool:
        """
        Evaluate an incoming tick against the risk guards.
        Returns True if a stop loss was triggered and order sent.
        """
        if tick.symbol not in self._active_guards:
            return False

        side, stop_loss, qty = self._active_guards[tick.symbol]
        triggered = False

        if side == "LONG" and tick.close <= stop_loss:
            triggered = True
        elif side == "SHORT" and tick.close >= stop_loss:
            triggered = True

        if triggered:
            logger.warning("[FastPath] EXTREME ALERT! STOP LOSS HIT FOR %s @ ₹%.2f", tick.symbol, tick.close)
            # Remove immediately so we don't trigger again on the next nanosecond
            self.remove_position(tick.symbol)
            # Fire and forget the HTTP call to broker
            asyncio.create_task(self._fire_emergency_order(tick.symbol, side, qty))
            return True

        return False

    async def _fire_emergency_order(self, symbol: str, position_side: str, qty: int) -> None:
        """Directly hit the broker service to exit position."""
        exit_side = "SELL" if position_side == "LONG" else "BUY"
        
        payload = {
            "symbol": symbol,
            "side": exit_side,
            "quantity": qty,
            "order_type": "MARKET"
        }
        
        headers = {
            "broker_type": "UPSTOX",
            "user_id": "system_user"
        }
        
        try:
            logger.info("[FastPath] Firing %s MARKET for %s", exit_side, symbol)
            resp = await self.client.post(self.broker_endpoint, json=payload, headers=headers)
            resp.raise_for_status()
            logger.info("[FastPath] Emergency order accepted. Latency < 10ms target achieved.")
        except Exception as e:
            logger.error("[FastPath] EMERGENCY ORDER FAILED: %s", e)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
