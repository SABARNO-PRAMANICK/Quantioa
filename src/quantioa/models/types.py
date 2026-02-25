"""Core data types (dataclasses) used throughout the trading platform."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from quantioa.models.enums import (
    AnomalyType,
    CircuitBreakerAction,
    ExecutionStrategy,
    OrderStatus,
    OrderType,
    OrderValidity,
    PositionStatus,
    ProductType,
    SentimentType,
    TradeSignal,
    TradeSide,
    VolatilityRegime,
)


# ─── Market Data ───────────────────────────────────────────────────────────────


@dataclass(slots=True)
class Tick:
    """Single market tick (OHLCV price update)."""

    timestamp: float
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(slots=True)
class Quote:
    """Normalized broker quote."""

    symbol: str
    price: float
    bid: float
    ask: float
    volume: float
    timestamp: float


@dataclass(slots=True)
class OrderBookLevel:
    """Single level in the order book (bid or ask)."""

    price: float
    quantity: int
    orders: int = 0


@dataclass(slots=True)
class OrderBookSnapshot:
    """Order book depth snapshot."""

    symbol: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    timestamp: float


# ─── Orders & Positions ───────────────────────────────────────────────────────


@dataclass
class Order:
    """Order to be placed with a broker."""

    symbol: str
    side: TradeSide
    quantity: int
    order_type: OrderType = OrderType.MARKET
    price: float | None = None  # Required for LIMIT orders
    stop_loss: float | None = None
    target: float | None = None
    product: ProductType = ProductType.INTRADAY
    validity: OrderValidity = OrderValidity.DAY
    trigger_price: float = 0.0  # For SL / SL-M orders
    tag: str = "quantioa"  # Order tag for tracking
    is_amo: bool = False  # After Market Order
    slice: bool = False  # Auto-slice large orders


@dataclass
class OrderResponse:
    """Normalized response after placing an order."""

    order_id: str
    status: OrderStatus
    symbol: str
    side: TradeSide
    quantity: int
    filled_price: float | None = None
    filled_quantity: int = 0
    message: str = ""
    timestamp: float = 0.0
    latency_ms: int = 0  # V3 API processing latency
    exchange_order_id: str = ""  # Exchange-assigned order ID
    average_price: float = 0.0  # Average fill price


@dataclass
class Position:
    """A currently held position."""

    id: str
    symbol: str
    side: TradeSide
    quantity: int
    entry_price: float
    current_price: float = 0.0
    stop_loss: float | None = None
    target: float | None = None
    entry_time: float = 0.0
    status: PositionStatus = PositionStatus.OPEN
    strategy_id: str = ""

    @property
    def unrealized_pnl(self) -> float:
        multiplier = 1.0 if self.side == TradeSide.LONG else -1.0
        return multiplier * (self.current_price - self.entry_price) * self.quantity

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        multiplier = 1.0 if self.side == TradeSide.LONG else -1.0
        return multiplier * (self.current_price - self.entry_price) / self.entry_price * 100


@dataclass
class TradeResult:
    """Completed trade (closed position)."""

    id: str
    symbol: str
    side: TradeSide
    quantity: int
    entry_price: float
    exit_price: float
    entry_time: float
    exit_time: float
    exit_reason: str = ""
    strategy_id: str = ""

    @property
    def pnl(self) -> float:
        multiplier = 1.0 if self.side == TradeSide.LONG else -1.0
        return multiplier * (self.exit_price - self.entry_price) * self.quantity

    @property
    def pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        multiplier = 1.0 if self.side == TradeSide.LONG else -1.0
        return multiplier * (self.exit_price - self.entry_price) / self.entry_price * 100

    @property
    def is_winner(self) -> bool:
        return self.pnl > 0

    @property
    def duration_seconds(self) -> float:
        return self.exit_time - self.entry_time


# ─── Indicator & Signal Outputs ────────────────────────────────────────────────


@dataclass
class IndicatorSnapshot:
    """Full snapshot of all indicator values at a point in time."""

    # Trend
    sma_20: float = 0.0
    sma_50: float = 0.0
    ema_9: float = 0.0
    ema_21: float = 0.0
    ema_55: float = 0.0

    # Momentum
    rsi: float = 50.0
    macd_line: float = 0.0
    macd_signal: float = 0.0
    macd_hist: float = 0.0

    # Volatility
    atr: float = 0.0
    keltner_upper: float = 0.0
    keltner_mid: float = 0.0
    keltner_lower: float = 0.0

    # Volume
    obv: float = 0.0
    vwap: float = 0.0

    # Binary signals
    signal_price_above_sma20: int = 0
    signal_ema_9_gt_21: int = 0
    signal_macd_positive: int = 0
    signal_rsi_oversold: int = 0
    signal_rsi_overbought: int = 0
    signal_price_above_vwap: int = 0


@dataclass
class SignalResult:
    """Output of the signal generation pipeline."""

    signal: TradeSignal
    strength: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    reasoning: str = ""
    technical_score: float = 0.0
    sentiment_score: float = 0.0
    mtf_agreement: float = 0.0
    regime: VolatilityRegime = VolatilityRegime.NORMAL
    kelly_position_size: float = 0.0
    recommended_stop_loss: float = 0.0
    recommended_target: float = 0.0


# ─── Risk ──────────────────────────────────────────────────────────────────────


@dataclass
class RiskMetrics:
    """Portfolio-level risk metrics."""

    current_equity: float = 0.0
    peak_equity: float = 0.0
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    drawdown_pct: float = 0.0
    daily_loss_pct: float = 0.0
    open_positions: int = 0
    is_trading_allowed: bool = True
    halt_reason: str = ""


@dataclass
class AnomalyEvent:
    """Detected market anomaly."""

    anomaly_type: AnomalyType
    severity: float  # z-score or ratio
    action: CircuitBreakerAction
    message: str
    timestamp: float = 0.0


# ─── Sentiment ─────────────────────────────────────────────────────────────────


@dataclass
class SentimentResult:
    """Output of sentiment analysis for a symbol."""

    symbol: str
    score: float  # -1.0 to +1.0
    sentiment_type: SentimentType
    confidence: float  # 0.0 to 1.0
    sources_count: int = 0
    headlines: list[str] = field(default_factory=list)
    timestamp: float = 0.0


# ─── Execution ─────────────────────────────────────────────────────────────────


@dataclass
class ExecutionPlan:
    """Recommended execution approach for an order."""

    strategy: ExecutionStrategy
    predicted_slippage_pct: float
    predicted_cost: float
    reasoning: str = ""


@dataclass
class ChildOrder:
    """A single child fill within a TWAP/VWAP parent execution."""

    order_id: str
    sequence: int  # 1-indexed slice number
    quantity: int
    target_price: float = 0.0
    filled_price: float = 0.0
    filled_quantity: int = 0
    status: OrderStatus = OrderStatus.PENDING
    scheduled_time: float = 0.0  # Unix timestamp for when this slice fires
    executed_time: float = 0.0
    slippage_bps: float = 0.0  # Actual slippage in basis points


@dataclass
class ParentOrder:
    """A parent order that may be split into child orders by TWAP/VWAP."""

    parent_id: str
    symbol: str
    side: TradeSide
    total_quantity: int
    strategy: ExecutionStrategy
    children: list[ChildOrder] = field(default_factory=list)
    filled_quantity: int = 0
    average_fill_price: float = 0.0
    created_at: float = 0.0
    completed_at: float = 0.0
    is_complete: bool = False

    @property
    def remaining_quantity(self) -> int:
        return self.total_quantity - self.filled_quantity

    @property
    def total_slippage_bps(self) -> float:
        if not self.children:
            return 0.0
        filled = [c for c in self.children if c.filled_quantity > 0]
        if not filled:
            return 0.0
        return sum(c.slippage_bps * c.filled_quantity for c in filled) / sum(
            c.filled_quantity for c in filled
        )


@dataclass
class IntentToTrade:
    """AI decision payload — emitted after the LLM finishes reasoning.

    The Trading Loop reads this after AI completes, then fetches fresh
    market data before executing.
    """

    symbol: str
    signal: TradeSignal
    confidence: float
    reasoning: str = ""
    suggested_quantity: int = 0
    suggested_stop_loss: float = 0.0
    suggested_target: float = 0.0
    ai_model: str = ""
    decision_timestamp: float = 0.0  # When the AI finished reasoning
    context_age_seconds: float = 0.0  # How old the input data was


@dataclass
class ExecutionMetrics:
    """Per-cycle latency and slippage tracking for the execution engine."""

    # Latency breakdown (microseconds)
    signal_gen_us: float = 0.0
    ai_decision_ms: float = 0.0  # AI call duration (milliseconds)
    data_refresh_us: float = 0.0  # Fresh data fetch after AI completes
    increment_reeval_us: float = 0.0  # Re-evaluation of OFI/Kelly/Vol
    slippage_calc_us: float = 0.0
    order_submit_us: float = 0.0
    total_execution_us: float = 0.0  # End-to-end after AI returns

    # Slippage
    predicted_slippage_bps: float = 0.0
    actual_slippage_bps: float = 0.0

    # Broker reported
    broker_latency_ms: int = 0
