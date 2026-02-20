"""
Orchestrates multi-symbol allocation for the trading engine.
"""

from typing import Dict, List, Optional
import logging

from quantioa.config import settings
from .universe import Universe, Nifty50Universe
from .correlation import CorrelationGuard
from .allocator import AssetAllocator
from .rebalancer import PortfolioRebalancer


logger = logging.getLogger(__name__)


class PortfolioManager:
    """Facade for the Portfolio Diversification Engine."""

    def __init__(self, universe: Optional[Universe] = None):
        self.universe = universe or Nifty50Universe()
        self.correlation_guard = CorrelationGuard(threshold=settings.correlation_threshold)
        self.allocator = AssetAllocator(self.universe)
        self.rebalancer = PortfolioRebalancer(self.universe)

    def is_trade_allowed(self, new_symbol: str, current_symbols: List[str]) -> bool:
        """
        Check if taking a new position violates the correlation limits.
        """
        # 1. Is it in our universe?
        if new_symbol not in self.universe.symbols:
            logger.warning(f"{new_symbol} not in allowed universe. Rejecting.")
            return False

        # 2. Check correlation
        if not self.correlation_guard.is_trade_allowed(new_symbol, current_symbols):
            logger.info(f"{new_symbol} rejected due to high correlation with existing holdings.")
            return False

        return True

    def allocate_capital(
        self,
        symbol: str,
        total_equity: float,
        current_positions: Dict[str, float],
        base_allocation_pct: Optional[float] = None
    ) -> float:
        """
        Calculate capital to allocate to a trade.
        Runs all allocator logic (stock max, sector max, cash min).
        """
        return self.allocator.calculate_allocation(
            symbol=symbol,
            total_equity=total_equity,
            current_positions=current_positions,
            base_allocation_pct=base_allocation_pct
        )

    def check_rebalance_needs(self, total_equity: float, current_positions: Dict[str, float]) -> List[Dict]:
        """
        Check for positions that have drifted beyond limits.
        """
        return self.rebalancer.check_drift(total_equity, current_positions)

    def update_price_history(self, symbol: str, price: float) -> None:
        """
        Update the rolling correlation guard with new closing prices.
        """
        self.correlation_guard.add_price_point(symbol, price)

