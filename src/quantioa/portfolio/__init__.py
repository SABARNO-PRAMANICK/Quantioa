"""
Portfolio Multi-Asset Allocation Engine
Handles symbol selection, position sizing, correlation guards, and rebalancing.
"""

from .universe import Nifty50Universe
from .correlation import CorrelationGuard
from .allocator import AssetAllocator
from .rebalancer import PortfolioRebalancer
from .manager import PortfolioManager

__all__ = [
    "Nifty50Universe",
    "CorrelationGuard",
    "AssetAllocator",
    "PortfolioRebalancer",
    "PortfolioManager"
]
