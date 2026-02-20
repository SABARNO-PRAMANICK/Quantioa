"""
Tests for the Portfolio Diversification Engine components.
"""

import pytest

from quantioa.portfolio.universe import Universe
from quantioa.portfolio.allocator import AssetAllocator
from quantioa.portfolio.correlation import CorrelationGuard
from quantioa.portfolio.manager import PortfolioManager


@pytest.fixture
def test_universe():
    return Universe({
        "TEST1": "IT",
        "TEST2": "IT",
        "TEST3": "Financial",
        "TEST4": "Energy",
        "TEST5": "IT",
        "TEST6": "Energy",
    })

def test_allocator_stock_limit(test_universe, monkeypatch):
    """Test standard Max per stock limit (20%) calculation."""
    from quantioa.portfolio import allocator
    monkeypatch.setattr(allocator.settings, "max_positions", 6)
    monkeypatch.setattr(allocator.settings, "max_per_stock_pct", 0.20)
    monkeypatch.setattr(allocator.settings, "max_per_sector_pct", 0.35)
    monkeypatch.setattr(allocator.settings, "min_cash_reserve_pct", 0.15)
    
    agent = AssetAllocator(test_universe)
    total_eq = 100000.0
    current_pos = {"TEST1": 15000.0} # 15% in TEST1

    # Want to add more to TEST1, max allowed should be 5000 (reach 20%)
    out = agent.calculate_allocation("TEST1", total_eq, current_pos, base_allocation_pct=0.10)
    assert out == 5000.0


def test_allocator_sector_limit(test_universe, monkeypatch):
    """Test max sector limit (35%)."""
    from quantioa.portfolio import allocator
    monkeypatch.setattr(allocator.settings, "max_positions", 6)
    monkeypatch.setattr(allocator.settings, "max_per_stock_pct", 0.20)
    monkeypatch.setattr(allocator.settings, "max_per_sector_pct", 0.35)
    monkeypatch.setattr(allocator.settings, "min_cash_reserve_pct", 0.15)
    
    agent = AssetAllocator(test_universe)
    total_eq = 100000.0
    # IT sector has 20000 (TEST1) + 10000 (TEST2) = 30000 (30%)
    current_pos = {"TEST1": 20000.0, "TEST2": 10000.0}

    # Want to add TEST5 (IT). Max allowed should be 5000.0 (reach 35% sector)
    out = agent.calculate_allocation("TEST5", total_eq, current_pos, base_allocation_pct=0.10)
    assert out == 5000.0

    # Want to add TEST3 (Financial). Max allowed should be bounded by stock limit 20000, 
    # but base alloc is 10000, so it gives 10000.
    out2 = agent.calculate_allocation("TEST3", total_eq, current_pos, base_allocation_pct=0.10)
    assert out2 == 10000.0


def test_correlation_guard():
    """Test correlation guard logic."""
    guard = CorrelationGuard(threshold=0.7)
    
    # 2 perfectly correlated assets
    prices_a = [10, 11, 12, 13, 14, 15]
    prices_b = [100, 110, 120, 130, 140, 150] # Matches a * 10
    
    for a, b in zip(prices_a, prices_b):
        guard.add_price_point("A", a)
        guard.add_price_point("B", b)

    assert guard.calculate_correlation("A", "B") > 0.99

    # Try entry
    assert not guard.is_trade_allowed("A", ["B"])

    # Independent asset
    prices_c = [10, 9, 10, 9, 10, 9]
    for c in prices_c:
        guard.add_price_point("C", c)
        
    assert guard.is_trade_allowed("C", ["A"])


def test_portfolio_manager_facade(test_universe, monkeypatch):
    """Integration style test for Portfolio Manager facade."""
    from quantioa.portfolio import manager
    monkeypatch.setattr(manager.settings, "max_positions", 6)
    monkeypatch.setattr(manager.settings, "max_per_stock_pct", 0.20)
    monkeypatch.setattr(manager.settings, "max_per_sector_pct", 0.35)
    monkeypatch.setattr(manager.settings, "correlation_threshold", 0.7)
    
    pm = PortfolioManager(universe=test_universe)
    
    # Not in universe
    assert not pm.is_trade_allowed("XYZ", [])
    
    # In universe, allowed
    assert pm.is_trade_allowed("TEST1", [])
    
    # Allocation
    total_eq = 1000.0
    current = {}
    
    # Base alloc uses 1/6th = ~16.66% = ~166.66
    alloc = pm.allocate_capital("TEST1", total_eq, current)
    assert alloc > 165.0 and alloc < 167.0
    
    # Check drift via rebalancer
    current = {"TEST1": 260.0} # 26%, max is 20%+5%
    actions = pm.check_rebalance_needs(total_eq, current)
    assert len(actions) == 1
    assert actions[0]["symbol"] == "TEST1"
    assert actions[0]["action"] == "REDUCE"
    assert actions[0]["amount_to_reduce"] == 60.0  # (260 - 200 = 60)
