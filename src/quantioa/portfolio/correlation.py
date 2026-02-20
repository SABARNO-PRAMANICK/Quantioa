"""
Rolling correlation matrix for the portfolio.
Blocks new trades if they are too highly correlated with existing holdings.
"""

from typing import Dict, List, Optional
import math


class CorrelationGuard:
    """Calculates Pearson correlation between assets to enforce diversification."""

    def __init__(self, threshold: float = 0.7):
        """
        Args:
            threshold: Maximum allowed Pearson correlation (default 0.7).
        """
        self.threshold = threshold
        self.price_history: Dict[str, List[float]] = {}
        # Keep maximum 50 periods for rolling window correlation
        self.window_size = 50

    def add_price_point(self, symbol: str, price: float) -> None:
        """Add a new price point for a symbol."""
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        
        self.price_history[symbol].append(price)
        if len(self.price_history[symbol]) > self.window_size:
            self.price_history[symbol].pop(0)

    def calculate_correlation(self, symbol_a: str, symbol_b: str) -> float:
        """Calculate Pearson correlation coefficient between two symbols."""
        if symbol_a not in self.price_history or symbol_b not in self.price_history:
            return 0.0  # Safe default if no data

        prices_a = self.price_history[symbol_a]
        prices_b = self.price_history[symbol_b]

        # Use the minimum length sequence available
        min_len = min(len(prices_a), len(prices_b))
        if min_len < 2:
            return 0.0

        a = prices_a[-min_len:]
        b = prices_b[-min_len:]

        mean_a = sum(a) / min_len
        mean_b = sum(b) / min_len

        numerator = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
        var_a = sum((x - mean_a) ** 2 for x in a)
        var_b = sum((y - mean_b) ** 2 for y in b)

        denominator = math.sqrt(var_a * var_b)
        if denominator == 0:
            return 0.0

        return numerator / denominator

    def is_trade_allowed(self, new_symbol: str, current_symbols: List[str]) -> bool:
        """
        Check if a new symbol exceeds the correlation threshold with any existing portfolio symbol.
        
        Args:
            new_symbol: The symbol being considered for entry.
            current_symbols: List of symbols currently held in the portfolio.
            
        Returns:
            True if trade is allowed (correlation <= threshold), False if blocked.
        """
        if not current_symbols:
            return True

        for existing_symbol in current_symbols:
            corr = self.calculate_correlation(new_symbol, existing_symbol)
            if corr > self.threshold:
                return False

        return True
