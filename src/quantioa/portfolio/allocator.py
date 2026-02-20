"""
Capital allocation with sector and stock limits.
"""

from typing import Dict, List, Optional
from decimal import Decimal

from quantioa.config import settings
from .universe import Universe


class AssetAllocator:
    """Manages capital allocation respecting sector and individual stock limits."""

    def __init__(self, universe: Universe):
        self.universe = universe
        self.max_positions = settings.max_positions
        self.max_per_stock_pct = settings.max_per_stock_pct
        self.max_per_sector_pct = settings.max_per_sector_pct
        self.min_cash_reserve_pct = settings.min_cash_reserve_pct

    def can_allocate(
        self,
        symbol: str,
        total_equity: float,
        current_positions: Dict[str, float]  # symbol -> position value in cash
    ) -> bool:
        """
        Check if taking a new position is allowed by sector/stock/cash limits.
        """
        if len(current_positions) >= self.max_positions and symbol not in current_positions:
            return False

        # Check existing allocation for this symbol
        current_stock_value = current_positions.get(symbol, 0.0)
        stock_pct = current_stock_value / total_equity if total_equity > 0 else 0.0
        if stock_pct >= self.max_per_stock_pct:
            return False

        # Check existing allocation for this sector
        sector = self.universe.get_sector(symbol)
        sector_value = sum(
            val for sym, val in current_positions.items() 
            if self.universe.get_sector(sym) == sector
        )
        sector_pct = sector_value / total_equity if total_equity > 0 else 0.0
        if sector_pct >= self.max_per_sector_pct and symbol not in current_positions:  # Adding new symbol in same sector
            return False

        return True

    def calculate_allocation(
        self,
        symbol: str,
        total_equity: float,
        current_positions: Dict[str, float],
        base_allocation_pct: float = None
    ) -> float:
        """
        Calculate the absolute capital amount to allocate to a trade.
        Returns 0.0 if limits prohibit allocation.
        """
        if not self.can_allocate(symbol, total_equity, current_positions):
            return 0.0

        # Base allocation: equally divide remaining allowed slots, or use Kelly fraction if provided
        if base_allocation_pct is None:
            # If 6 max positions, base is ~16.6% per name
            base_allocation_pct = 1.0 / self.max_positions

        target_allocation_value = total_equity * base_allocation_pct

        # Check cash constraints
        total_invested = sum(current_positions.values())
        available_cash = total_equity - total_invested
        min_required_cash = total_equity * self.min_cash_reserve_pct
        usable_cash = available_cash - min_required_cash

        if usable_cash <= 0:
            return 0.0

        # Constrain by max_per_stock (how much more can we add?)
        current_stock_value = current_positions.get(symbol, 0.0)
        max_allowed_for_stock = (total_equity * self.max_per_stock_pct) - current_stock_value

        # Constrain by max_per_sector (how much more can we add to this sector?)
        sector = self.universe.get_sector(symbol)
        sector_value = sum(
            val for sym, val in current_positions.items() 
            if self.universe.get_sector(sym) == sector
        )
        max_allowed_for_sector = (total_equity * self.max_per_sector_pct) - sector_value

        # The actual allocated amount is bounded by all constraints
        allocate_amount = min(
            target_allocation_value,
            usable_cash,
            max_allowed_for_stock,
            max_allowed_for_sector
        )

        return max(allocate_amount, 0.0)
