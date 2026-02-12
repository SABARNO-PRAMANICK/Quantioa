"""Core enums used throughout the trading platform."""

from __future__ import annotations

from enum import Enum


# ─── Trading Signals ───────────────────────────────────────────────────────────


class TradeSignal(str, Enum):
    """Output of signal generators."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class TradeSide(str, Enum):
    """Direction of a position."""

    LONG = "LONG"
    SHORT = "SHORT"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PENDING = "PENDING"


# ─── Volatility & Regimes ─────────────────────────────────────────────────────


class VolatilityRegime(str, Enum):
    """Market volatility classification."""

    EXTREME_LOW_VOL = "EXTREME_LOW_VOL"  # < 1%
    LOW_VOL = "LOW_VOL"                  # 1-3%
    NORMAL = "NORMAL"                    # 3-6%
    HIGH_VOL = "HIGH_VOL"               # 6-10%
    EXTREME_VOL = "EXTREME_VOL"         # > 10%


# ─── Strategies ────────────────────────────────────────────────────────────────


class StrategyType(str, Enum):
    MEAN_REVERSION = "MEAN_REVERSION"
    MOMENTUM = "MOMENTUM"
    BREAKOUT = "BREAKOUT"
    TREND_FOLLOWING = "TREND_FOLLOWING"
    MULTI_INCREMENT = "MULTI_INCREMENT"
    CUSTOM_LLM = "CUSTOM_LLM"


class StrategyStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


# ─── Anomaly Detection ────────────────────────────────────────────────────────


class AnomalyType(str, Enum):
    PRICE_ANOMALY = "PRICE_ANOMALY"
    BLACK_SWAN = "BLACK_SWAN"
    VOLUME_SPIKE = "VOLUME_SPIKE"
    POTENTIAL_GAP = "POTENTIAL_GAP"
    LIQUIDITY_CRISIS = "LIQUIDITY_CRISIS"


class CircuitBreakerAction(str, Enum):
    NONE = "NONE"
    REDUCE_SIZE = "REDUCE_SIZE"        # -30% position size
    TIGHTEN_STOPS = "TIGHTEN_STOPS"    # 1.5x tighter stops
    HALT_AND_CLOSE = "HALT_AND_CLOSE"  # Close all, halt 15 min
    HALT_ALL = "HALT_ALL"              # Close all, halt 30 min


# ─── Execution ─────────────────────────────────────────────────────────────────


class ExecutionStrategy(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    TWAP = "TWAP"
    VWAP = "VWAP"


# ─── Sentiment ─────────────────────────────────────────────────────────────────


class SentimentType(str, Enum):
    EXTREME_BEARISH = "EXTREME_BEARISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    BULLISH = "BULLISH"
    EXTREME_BULLISH = "EXTREME_BULLISH"


# ─── User & Subscription ──────────────────────────────────────────────────────


class UserRole(str, Enum):
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    BROKER_ADMIN = "BROKER_ADMIN"
    INSTITUTION_ADMIN = "INSTITUTION_ADMIN"
    FREE_TRADER = "FREE_TRADER"
    PRO_TRADER = "PRO_TRADER"
    PREMIUM_TRADER = "PREMIUM_TRADER"


class SubscriptionTier(str, Enum):
    FREE = "FREE"
    PRO = "PRO"
    PREMIUM = "PREMIUM"
    ENTERPRISE = "ENTERPRISE"


class BrokerType(str, Enum):
    UPSTOX = "UPSTOX"
    ZERODHA = "ZERODHA"
    SHOONJE = "SHOONJE"


class RiskTolerance(str, Enum):
    CONSERVATIVE = "CONSERVATIVE"
    MODERATE = "MODERATE"
    AGGRESSIVE = "AGGRESSIVE"


class TradingExperience(str, Enum):
    BEGINNER = "BEGINNER"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"
