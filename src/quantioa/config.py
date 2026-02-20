"""
Central configuration for the Quantioa trading platform.

All settings are loaded from environment variables with sensible defaults.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import Field
from pydantic_settings import BaseSettings


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- Environment ---
    env: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"

    # --- Upstox Broker API ---
    upstox_api_key: str = ""
    upstox_api_secret: str = ""
    upstox_redirect_uri: str = "http://localhost:8000/api/v1/oauth/upstox/callback"
    upstox_base_url: str = "https://api.upstox.com/v2"
    upstox_hft_base_url: str = "https://api-hft.upstox.com/v3"
    upstox_auth_url: str = "https://api.upstox.com/v2/login/authorization/dialog"
    upstox_token_url: str = "https://api.upstox.com/v2/login/authorization/token"
    upstox_ws_url: str = "wss://api.upstox.com/v2/feed/market-data-feed"
    upstox_ws_market_auth_url: str = "https://api.upstox.com/v3/feed/market-data-feed/authorize"
    upstox_ws_portfolio_url: str = "wss://api.upstox.com/v2/feed/portfolio-stream-feed"
    upstox_sandbox_mode: bool = False
    upstox_webhook_enabled: bool = False

    # --- Zerodha Broker API ---
    zerodha_api_key: str = ""
    zerodha_api_secret: str = ""
    zerodha_redirect_uri: str = "http://localhost:8000/api/v1/oauth/zerodha/callback"
    zerodha_base_url: str = "https://api.kite.trade"
    zerodha_auth_url: str = "https://kite.zerodha.com/connect/login"


    # --- OpenRouter (AI model + Perplexity) ---
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    ai_model: str = "moonshotai/kimi-k2.5"
    perplexity_model: str = "perplexity/sonar-pro"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Kafka ---
    kafka_bootstrap_servers: str = "localhost:9092"

    # --- JWT Auth ---
    jwt_secret_key: str = ""  # REQUIRED — set via JWT_SECRET_KEY env var
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 30

    # --- Trading Defaults ---
    default_stop_loss_pct: float = 2.0
    default_kelly_fraction: float = 0.25
    max_daily_loss_pct: float = 2.0
    max_weekly_drawdown_pct: float = 5.0
    trading_loop_interval_seconds: int = 30
    min_trade_history_for_kelly: int = 20

    # --- Circuit Breaker Thresholds ---
    zscore_anomaly_threshold: float = 3.0
    zscore_black_swan_threshold: float = 5.0
    volume_spike_threshold: float = 3.0
    volume_gap_threshold: float = 5.0
    spread_crisis_threshold: float = 2.0
    circuit_breaker_halt_minutes: int = 30

    # --- Volatility Regime Thresholds (ATR/Close %) ---
    extreme_low_vol_threshold: float = 1.0
    low_vol_threshold: float = 3.0
    normal_vol_threshold: float = 6.0
    high_vol_threshold: float = 10.0
    # Above high_vol_threshold = EXTREME_VOL

    # --- Signal Thresholds ---
    min_confidence_threshold: float = 0.65
    min_signal_strength: float = 0.5
    min_risk_reward_ratio: float = 1.5
    min_mtf_agreement: float = 0.67

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# ─── Tier-Based Rate Limits & Quotas ───────────────────────────────────────────


class TierLimits:
    """Resource quotas per subscription tier."""

    TIERS: dict[str, dict] = {
        "FREE": {
            "api_calls_per_hour": 100,
            "max_strategies": 2,
            "live_trading": False,
            "max_capital": Decimal("0"),
            "llm_calls_per_day": 50,
            "max_concurrent_positions": 1,
            "max_broker_accounts": 1,
        },
        "PRO": {
            "api_calls_per_hour": 1_000,
            "max_strategies": 10,
            "live_trading": True,
            "max_capital": Decimal("500_000"),
            "llm_calls_per_day": 1_000,
            "max_concurrent_positions": 5,
            "max_broker_accounts": 3,
        },
        "PREMIUM": {
            "api_calls_per_hour": 10_000,
            "max_strategies": 100,
            "live_trading": True,
            "max_capital": None,  # Unlimited
            "llm_calls_per_day": 50_000,
            "max_concurrent_positions": 50,
            "max_broker_accounts": 10,
        },
    }

    @classmethod
    def get(cls, tier: str) -> dict:
        return cls.TIERS.get(tier.upper(), cls.TIERS["FREE"])


# Singleton settings instance
settings = Settings()
