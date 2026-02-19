"""
Unit tests for data models (Position, TradeResult, TokenPair).

Tests: computed properties (PnL, is_winner, duration, is_expired).
"""

import time
import pytest

from quantioa.models.enums import TradeSide
from quantioa.models.types import Position, TradeResult
from quantioa.broker.types import TokenPair


class TestPositionPnL:
    def test_long_profit(self):
        p = Position(
            id="P1", symbol="INFY", side=TradeSide.LONG,
            quantity=10, entry_price=1500.0, current_price=1600.0,
        )
        assert p.unrealized_pnl == 1000.0  # (1600-1500)*10
        assert p.unrealized_pnl_pct == pytest.approx(6.67, abs=0.01)

    def test_long_loss(self):
        p = Position(
            id="P2", symbol="INFY", side=TradeSide.LONG,
            quantity=5, entry_price=1500.0, current_price=1400.0,
        )
        assert p.unrealized_pnl == -500.0
        assert p.unrealized_pnl_pct == pytest.approx(-6.67, abs=0.01)

    def test_short_profit(self):
        p = Position(
            id="P3", symbol="SBIN", side=TradeSide.SHORT,
            quantity=10, entry_price=500.0, current_price=480.0,
        )
        assert p.unrealized_pnl == 200.0  # (500-480)*10, short = reversed

    def test_short_loss(self):
        p = Position(
            id="P4", symbol="SBIN", side=TradeSide.SHORT,
            quantity=10, entry_price=500.0, current_price=520.0,
        )
        assert p.unrealized_pnl == -200.0

    def test_zero_entry_price(self):
        p = Position(
            id="P5", symbol="X", side=TradeSide.LONG,
            quantity=1, entry_price=0.0, current_price=100.0,
        )
        assert p.unrealized_pnl_pct == 0.0

    def test_flat_position(self):
        p = Position(
            id="P6", symbol="X", side=TradeSide.LONG,
            quantity=1, entry_price=100.0, current_price=100.0,
        )
        assert p.unrealized_pnl == 0.0
        assert p.unrealized_pnl_pct == 0.0


class TestTradeResult:
    def test_long_winner(self):
        t = TradeResult(
            id="T1", symbol="INFY", side=TradeSide.LONG,
            quantity=10, entry_price=1500.0, exit_price=1600.0,
            entry_time=0.0, exit_time=3600.0,
        )
        assert t.pnl == 1000.0
        assert t.is_winner is True
        assert t.duration_seconds == 3600.0

    def test_long_loser(self):
        t = TradeResult(
            id="T2", symbol="INFY", side=TradeSide.LONG,
            quantity=5, entry_price=1500.0, exit_price=1400.0,
            entry_time=0.0, exit_time=1800.0,
        )
        assert t.pnl == -500.0
        assert t.is_winner is False

    def test_short_winner(self):
        t = TradeResult(
            id="T3", symbol="SBIN", side=TradeSide.SHORT,
            quantity=10, entry_price=500.0, exit_price=480.0,
            entry_time=0.0, exit_time=60.0,
        )
        assert t.pnl == 200.0
        assert t.is_winner is True

    def test_short_loser(self):
        t = TradeResult(
            id="T4", symbol="SBIN", side=TradeSide.SHORT,
            quantity=10, entry_price=500.0, exit_price=520.0,
            entry_time=0.0, exit_time=60.0,
        )
        assert t.pnl == -200.0
        assert t.is_winner is False

    def test_pnl_pct(self):
        t = TradeResult(
            id="T5", symbol="X", side=TradeSide.LONG,
            quantity=1, entry_price=100.0, exit_price=110.0,
            entry_time=0.0, exit_time=1.0,
        )
        assert t.pnl_pct == pytest.approx(10.0)

    def test_zero_entry_price_pnl_pct(self):
        t = TradeResult(
            id="T6", symbol="X", side=TradeSide.LONG,
            quantity=1, entry_price=0.0, exit_price=100.0,
            entry_time=0.0, exit_time=1.0,
        )
        assert t.pnl_pct == 0.0

    def test_exit_reason(self):
        t = TradeResult(
            id="T7", symbol="X", side=TradeSide.LONG,
            quantity=1, entry_price=100.0, exit_price=90.0,
            entry_time=0.0, exit_time=1.0, exit_reason="STOP_LOSS",
        )
        assert t.exit_reason == "STOP_LOSS"


class TestTokenPair:
    def test_not_expired(self):
        t = TokenPair(access_token="test", expires_at=time.time() + 3600)
        assert t.is_expired is False

    def test_expired(self):
        t = TokenPair(access_token="test", expires_at=time.time() - 3600)
        assert t.is_expired is True

    def test_expired_within_buffer(self):
        """Token within 5-minute buffer before expiry is considered expired."""
        t = TokenPair(access_token="test", expires_at=time.time() + 200)
        assert t.is_expired is True  # 200s < 300s buffer

    def test_default_fields(self):
        t = TokenPair(access_token="test")
        assert t.token_type == "Bearer"
        assert t.refresh_token == ""
        assert t.exchanges == []
        assert t.products == []
