"""
Paper Trading Adapter — simulated broker for testing.

Tracks virtual positions, P&L, and order history without
touching any real broker API. Behaves identically to UpstoxAdapter
so the trading loop doesn't know the difference.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from quantioa.broker.base import BrokerAdapter
from quantioa.models.enums import OrderStatus, TradeSide
from quantioa.models.types import (
    Order,
    OrderBookLevel,
    OrderBookSnapshot,
    OrderResponse,
    Position,
    Quote,
)

logger = logging.getLogger(__name__)


@dataclass
class PaperPosition:
    """A simulated open position."""

    symbol: str
    side: str  # "LONG" or "SHORT"
    quantity: int
    entry_price: float
    timestamp: float = 0.0

    def unrealized_pnl(self, current_price: float) -> float:
        if self.side == "LONG":
            return (current_price - self.entry_price) * self.quantity
        return (self.entry_price - current_price) * self.quantity


@dataclass
class PaperOrder:
    """A simulated order record."""

    order_id: str
    symbol: str
    side: str
    quantity: int
    price: float
    status: str = "FILLED"
    timestamp: float = 0.0


class PaperTradingAdapter(BrokerAdapter):
    """Simulated broker for paper trading and backtesting.

    Usage:
        adapter = PaperTradingAdapter(initial_capital=100_000)
        await adapter.connect()

        # Set current prices (simulate market data)
        adapter.set_price("NIFTY50", 22150.0)

        # Place orders like a real broker
        resp = await adapter.place_order(order)

        # Check P&L
        print(adapter.summary())
    """

    def __init__(self, initial_capital: float = 100_000.0) -> None:
        self._initial_capital = initial_capital
        self._cash = initial_capital
        self._positions: dict[str, PaperPosition] = {}
        self._orders: list[PaperOrder] = []
        self._prices: dict[str, float] = {}
        self._order_counter = 0
        self._connected = False
        self._realized_pnl = 0.0

    # ─── Price Feed ────────────────────────────────────────────────────────

    def set_price(self, symbol: str, price: float) -> None:
        """Update current market price for a symbol."""
        self._prices[symbol] = price

    # ─── BrokerAdapter Interface ───────────────────────────────────────────

    async def connect(self) -> None:
        self._connected = True
        logger.info("Paper trading connected (capital: ₹%.0f)", self._initial_capital)

    async def disconnect(self) -> None:
        self._connected = False

    async def get_quote(self, symbol: str) -> Quote:
        price = self._prices.get(symbol, 0.0)
        return Quote(
            symbol=symbol,
            price=price,
            bid=round(price * 0.9999, 2),
            ask=round(price * 1.0001, 2),
            volume=10000,
            timestamp=time.time(),
        )

    async def get_order_book_snapshot(self, symbol: str) -> OrderBookSnapshot:
        price = self._prices.get(symbol, 0.0)
        return OrderBookSnapshot(
            symbol=symbol,
            bids=[OrderBookLevel(price=round(price * 0.999, 2), quantity=100)],
            asks=[OrderBookLevel(price=round(price * 1.001, 2), quantity=100)],
            timestamp=time.time(),
        )

    async def get_order_book(self, symbol: str) -> dict:
        return {"bids": [], "asks": [], "symbol": symbol}

    async def place_order(self, order: Order) -> OrderResponse:
        """Simulate order fill at current market price."""
        symbol = order.symbol
        price = self._prices.get(symbol, order.price or 0.0)
        qty = order.quantity
        side = order.side.value if hasattr(order.side, "value") else str(order.side)
        side_enum = order.side if isinstance(order.side, TradeSide) else TradeSide(side)

        self._order_counter += 1
        order_id = f"PAPER-{self._order_counter:04d}"

        # Check if closing an existing position
        if symbol in self._positions:
            pos = self._positions[symbol]
            if (side == "SHORT" and pos.side == "LONG") or (side == "LONG" and pos.side == "SHORT"):
                # Close position
                pnl = pos.unrealized_pnl(price)
                self._realized_pnl += pnl
                self._cash += pos.entry_price * pos.quantity + pnl
                del self._positions[symbol]
                logger.info(
                    "PAPER CLOSE %s %s @ ₹%.2f | P&L: ₹%.2f",
                    side, symbol, price, pnl,
                )
            else:
                # Add to position
                total_qty = pos.quantity + qty
                pos.entry_price = (pos.entry_price * pos.quantity + price * qty) / total_qty
                pos.quantity = total_qty
        else:
            # Open new position
            self._positions[symbol] = PaperPosition(
                symbol=symbol,
                side=side,
                quantity=qty,
                entry_price=price,
                timestamp=time.time(),
            )
            self._cash -= price * qty
            logger.info("PAPER OPEN %s %s x%d @ ₹%.2f", side, symbol, qty, price)

        paper_order = PaperOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=qty,
            price=price,
            timestamp=time.time(),
        )
        self._orders.append(paper_order)

        return OrderResponse(
            order_id=order_id,
            status=OrderStatus.FILLED,
            symbol=symbol,
            side=side_enum,
            quantity=qty,
            filled_price=price,
            filled_quantity=qty,
            timestamp=time.time(),
        )

    async def cancel_order(self, order_id: str) -> bool:
        return True

    async def get_holdings(self) -> list[Position]:
        return []

    async def get_account_balance(self) -> float:
        return self._cash

    async def get_positions(self) -> list[Position]:
        result = []
        for idx, pos in enumerate(self._positions.values()):
            current_price = self._prices.get(pos.symbol, pos.entry_price)
            side_enum = TradeSide.LONG if pos.side == "LONG" else TradeSide.SHORT
            result.append(Position(
                id=f"PP-{idx}",
                symbol=pos.symbol,
                side=side_enum,
                quantity=pos.quantity,
                entry_price=pos.entry_price,
                current_price=current_price,
            ))
        return result

    async def get_balance(self) -> dict:
        unrealized = sum(
            p.unrealized_pnl(self._prices.get(p.symbol, p.entry_price))
            for p in self._positions.values()
        )
        return {
            "cash": round(self._cash, 2),
            "unrealized_pnl": round(unrealized, 2),
            "realized_pnl": round(self._realized_pnl, 2),
            "total_equity": round(self._cash + unrealized, 2),
            "initial_capital": self._initial_capital,
        }

    # ─── Paper-Specific ───────────────────────────────────────────────────

    def summary(self) -> str:
        """Human-readable account summary."""
        bal = {
            "cash": self._cash,
            "realized_pnl": self._realized_pnl,
            "positions": len(self._positions),
            "total_orders": len(self._orders),
        }
        unrealized = sum(
            p.unrealized_pnl(self._prices.get(p.symbol, p.entry_price))
            for p in self._positions.values()
        )
        total = self._cash + unrealized
        pnl_pct = ((total / self._initial_capital) - 1) * 100

        return (
            f"=== Paper Trading Summary ===\n"
            f"Initial Capital: ₹{self._initial_capital:,.0f}\n"
            f"Cash:            ₹{self._cash:,.0f}\n"
            f"Unrealized P&L:  ₹{unrealized:,.0f}\n"
            f"Realized P&L:    ₹{self._realized_pnl:,.0f}\n"
            f"Total Equity:    ₹{total:,.0f}\n"
            f"Return:          {pnl_pct:+.2f}%\n"
            f"Open Positions:  {len(self._positions)}\n"
            f"Total Orders:    {len(self._orders)}"
        )
