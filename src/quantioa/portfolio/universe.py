"""
Universe definitions for stock selection.
Provides statically grouped indices and dynamic filtering capabilities.
"""

from typing import Dict, List, Set


class Universe:
    """Base class for market universes."""

    def __init__(self, constituents: Dict[str, str]):
        """
        Args:
            constituents: Mapping of symbol -> sector
        """
        self._constituents = constituents
        self._sectors = set(constituents.values())

    @property
    def symbols(self) -> List[str]:
        return list(self._constituents.keys())

    def get_sector(self, symbol: str) -> str:
        """Returns the sector for a given symbol, or 'Unknown' if not found."""
        return self._constituents.get(symbol, "Unknown")

    def get_symbols_by_sector(self, sector: str) -> List[str]:
        """Returns all symbols belonging to a specific sector."""
        return [sym for sym, sec in self._constituents.items() if sec == sector]


# Static representation of NIFTY 50 universe with sample sectors.
# Ideally this would be loaded from a DB or API.
NIFTY_50_STOCKS = {
    "RELIANCE": "Energy",
    "TCS": "IT",
    "HDFCBANK": "Financial Services",
    "ICICIBANK": "Financial Services",
    "BHARTIARTL": "Telecommunication",
    "SBIN": "Financial Services",
    "INFY": "IT",
    "L&T": "Construction",
    "ITC": "Fast Moving Consumer Goods",
    "BAJFINANCE": "Financial Services",
    "HINDUNILVR": "Fast Moving Consumer Goods",
    "LT": "Construction", # Sometimes mapped this way
    "AXISBANK": "Financial Services",
    "KOTAKBANK": "Financial Services",
    "TATAMOTORS": "Automobile and Auto Components",
    "MARUTI": "Automobile and Auto Components",
    "M&M": "Automobile and Auto Components",
    "SUNPHARMA": "Healthcare",
    "HCLTECH": "IT",
    "ASIANPAINT": "Consumer Durables",
    "TITAN": "Consumer Durables",
    "NTPC": "Power",
    "TATASTEEL": "Metals & Mining",
    "ULTRACEMCO": "Construction Materials",
    "BAJAJFINSV": "Financial Services",
    "ADANIENT": "Metals & Mining",
    "WIPRO": "IT",
    "POWERGRID": "Power",
    "COALINDIA": "Metals & Mining",
    "ONGC": "Energy",
    "HDFCLIFE": "Financial Services",
    "HEROMOTOCO": "Automobile and Auto Components",
    "HINDALCO": "Metals & Mining",
    "TECHM": "IT",
    "EICHERMOT": "Automobile and Auto Components",
    "TATACONSUM": "Fast Moving Consumer Goods",
    "JSWSTEEL": "Metals & Mining",
    "GRASIM": "Construction Materials",
    "DRREDDY": "Healthcare",
    "CIPLA": "Healthcare",
    "SBILIFE": "Financial Services",
    "BRITANNIA": "Fast Moving Consumer Goods",
    "BAJAJ-AUTO": "Automobile and Auto Components",
    "APOLLOHOSP": "Healthcare",
    "ADANIPORTS": "Services",
    "INDUSINDBK": "Financial Services",
    "DIVISLAB": "Healthcare",
    "BPCL": "Energy",
    "SHRIRAMFIN": "Financial Services",
    "TRENT": "Services",
    "BEML": "Capital Goods"
}

class Nifty50Universe(Universe):
    """NIFTY 50 Trading Universe."""
    def __init__(self):
        super().__init__(NIFTY_50_STOCKS)
