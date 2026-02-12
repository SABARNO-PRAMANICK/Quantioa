"""
Abstract base class for broker adapters.

All broker integrations (Upstox, Zerodha, Shoonje) implement this interface
so the trading engine can call adapter.place_order() without caring which
broker is being used.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from quantioa.models.types import (
    Order,
    OrderBookSnapshot,
    OrderResponse,
    Position,
    Quote,
)


class BrokerAdapter(ABC):
    """Abstract broker adapter interface.

    Concrete implementations normalize broker-specific API responses
    into common types (Quote, OrderResponse, Position).
    """

    @abstractmethod
    async def connect(self) -> None:
        """Initialize connection / validate credentials."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Clean up connections."""
        ...

    @abstractmethod
    async def get_quote(self, symbol: str) -> Quote:
        """Get a live quote for a symbol."""
        ...

    @abstractmethod
    async def get_order_book_snapshot(self, symbol: str) -> OrderBookSnapshot:
        """Get the current order book depth for a symbol."""
        ...

    @abstractmethod
    async def place_order(self, order: Order) -> OrderResponse:
        """Place a buy/sell order. Returns normalized response."""
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order. Returns True if successful."""
        ...

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Get all open positions."""
        ...

    @abstractmethod
    async def get_holdings(self) -> list[Position]:
        """Get holdings (delivery positions)."""
        ...

    @abstractmethod
    async def get_account_balance(self) -> float:
        """Get available account balance / margin."""
        ...
