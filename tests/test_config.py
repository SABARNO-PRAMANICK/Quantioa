"""
Unit tests for the config module.

Tests: TierLimits.get(), Settings defaults, environment variable override.
"""

import pytest
from decimal import Decimal

from quantioa.config import TierLimits, Settings


class TestTierLimits:
    def test_free_tier(self):
        limits = TierLimits.get("FREE")
        assert limits["live_trading"] is False
        assert limits["max_strategies"] == 2
        assert limits["max_capital"] == Decimal("0")
        assert limits["api_calls_per_hour"] == 100

    def test_pro_tier(self):
        limits = TierLimits.get("PRO")
        assert limits["live_trading"] is True
        assert limits["max_strategies"] == 10
        assert limits["max_capital"] == Decimal("500_000")
        assert limits["llm_calls_per_day"] == 1_000

    def test_premium_tier(self):
        limits = TierLimits.get("PREMIUM")
        assert limits["live_trading"] is True
        assert limits["max_capital"] is None  # Unlimited
        assert limits["max_concurrent_positions"] == 50

    def test_case_insensitive(self):
        assert TierLimits.get("free") == TierLimits.get("FREE")
        assert TierLimits.get("Pro") == TierLimits.get("PRO")

    def test_unknown_tier_returns_free(self):
        assert TierLimits.get("UNKNOWN") == TierLimits.get("FREE")
        assert TierLimits.get("") == TierLimits.get("FREE")


class TestSettingsDefaults:
    def test_default_ai_model(self):
        s = Settings()
        assert s.ai_model == "moonshotai/kimi-k2.5"

    def test_default_perplexity_model(self):
        s = Settings()
        assert s.perplexity_model == "perplexity/sonar-pro"

    def test_default_redis_url(self):
        s = Settings()
        assert s.redis_url == "redis://localhost:6379/0"

    def test_default_kafka_bootstrap_servers(self):
        s = Settings()
        assert s.kafka_bootstrap_servers == "localhost:9092"

    def test_default_risk_params(self):
        s = Settings()
        assert s.default_stop_loss_pct == 2.0
        assert s.max_daily_loss_pct == 2.0

    def test_default_kelly_fraction(self):
        s = Settings()
        assert 0 < s.default_kelly_fraction <= 1.0
