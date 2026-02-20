"""
Drift detection and rebalancing triggers.
Emits signals when portfolio weights drift beyond configured limits.
"""

from typing import Dict, List

from quantioa.config import settings
from .universe import Universe


class PortfolioRebalancer:
    """Detects when positions have drifted beyond acceptable limits and need rebalancing."""

    def __init__(self, universe: Universe):
        self.universe = universe
        self.max_per_stock_pct = settings.max_per_stock_pct
        self.max_per_sector_pct = settings.max_per_sector_pct
        
        # Buffer before triggering an immediate rebalance (e.g. 20% limit + 5% drift = 25% threshold)
        self.drift_buffer_pct = 0.05

    def check_drift(self, total_equity: float, current_positions: Dict[str, float]) -> List[Dict]:
        """
        Check all current positions to see if they exceed limits by drift.
        Returns a list of required rebalancing actions (e.g., {"symbol": "INFY", "action": "REDUCE", "amount": 5000})
        """
        if total_equity <= 0:
            return []

        actions = []
        sector_values = {}

        for symbol, value in current_positions.items():
            stock_pct = value / total_equity
            
            # Record sector values
            sector = self.universe.get_sector(symbol)
            sector_values[sector] = sector_values.get(sector, 0.0) + value
            
            # Check individual stock drift
            drift_limit = self.max_per_stock_pct + self.drift_buffer_pct
            if stock_pct > drift_limit:
                excess_value = value - (total_equity * self.max_per_stock_pct)
                actions.append({
                    "symbol": symbol,
                    "action": "REDUCE",
                    "reason": "STOCK_CONCENTRATION",
                    "excess_pct": stock_pct - self.max_per_stock_pct,
                    "amount_to_reduce": excess_value
                })

        # Check sector drift
        for sector, value in sector_values.items():
            sector_pct = value / total_equity
            drift_limit = self.max_per_sector_pct + self.drift_buffer_pct
            if sector_pct > drift_limit:
                # Find the largest holding in this sector to reduce
                sector_symbols = [
                    sym for sym in current_positions.keys() 
                    if self.universe.get_sector(sym) == sector
                ]
                
                # Sort by position size descending
                sector_symbols.sort(key=lambda s: current_positions[s], reverse=True)
                
                # We'll tag the largest symbol for reduction to fix sector breach
                largest_symbol = sector_symbols[0]
                excess_value = value - (total_equity * self.max_per_sector_pct)
                
                # Only add if we haven't already tagged it for stock drift (or we could merge them)
                if not any(a["symbol"] == largest_symbol for a in actions):
                    actions.append({
                        "symbol": largest_symbol,
                        "action": "REDUCE",
                        "reason": "SECTOR_CONCENTRATION",
                        "excess_pct": sector_pct - self.max_per_sector_pct,
                        "amount_to_reduce": excess_value
                    })

        return actions
