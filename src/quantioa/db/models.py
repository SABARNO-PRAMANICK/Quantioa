"""
SQLAlchemy ORM models for the Quantioa trading platform.

All tables use user_id foreign keys for multi-tenant isolation.
Indexes are designed for the most common query patterns:
- User lookup by email
- Trades by user + symbol + time range
- AI decision log by user + symbol (5-year SEBI audit trail)
- Broker accounts by user + broker type
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from quantioa.db.base import Base


# ── Helpers ──────────────────────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# ── Users ────────────────────────────────────────────────────────────────────


class User(Base):
    """Platform user — the root of all multi-tenant data.

    Every table references ``user_id`` for tenant isolation.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="FREE_TRADER")
    subscription_tier: Mapped[str] = mapped_column(String(32), default="FREE")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # KYC / compliance (Phase 3)
    full_name: Mapped[str | None] = mapped_column(String(256))
    pan_number: Mapped[str | None] = mapped_column(String(10))  # Indian PAN
    kyc_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_disclosure_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Risk preferences
    risk_tolerance: Mapped[str] = mapped_column(String(32), default="MODERATE")
    max_daily_loss_pct: Mapped[float] = mapped_column(Numeric(8, 4), default=2.0)
    max_weekly_drawdown_pct: Mapped[float] = mapped_column(Numeric(8, 4), default=5.0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    broker_accounts: Mapped[list[BrokerAccount]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    trades: Mapped[list[Trade]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    ai_decisions: Mapped[list[AIDecisionLog]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.email} role={self.role}>"


# ── Broker Accounts ──────────────────────────────────────────────────────────


class BrokerAccount(Base):
    """Linked broker account (Upstox, Zerodha, etc).

    Stores encrypted tokens — one row per user per broker.
    """

    __tablename__ = "broker_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "broker_type", name="uq_user_broker"),
        Index("ix_broker_user_type", "user_id", "broker_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    broker_type: Mapped[str] = mapped_column(String(32), nullable=False)  # UPSTOX, ZERODHA
    broker_user_id: Mapped[str] = mapped_column(String(64), default="")

    # Tokens (encrypted at rest in production via Phase 3)
    access_token: Mapped[str] = mapped_column(Text, default="")
    refresh_token: Mapped[str] = mapped_column(Text, default="")
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Allowed exchanges
    exchanges: Mapped[dict | None] = mapped_column(JSONB)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationship
    user: Mapped[User] = relationship(back_populates="broker_accounts")

    def __repr__(self) -> str:
        return f"<BrokerAccount user={self.user_id} broker={self.broker_type}>"


# ── Trades ───────────────────────────────────────────────────────────────────


class Trade(Base):
    """Executed trade record — full lifecycle from signal to fill.

    Stores both the AI reasoning and the execution details for
    SEBI 5-year audit trail compliance.
    """

    __tablename__ = "trades"
    __table_args__ = (
        Index("ix_trade_user_symbol", "user_id", "symbol"),
        Index("ix_trade_user_time", "user_id", "created_at"),
        Index("ix_trade_strategy", "strategy_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # LONG, SHORT
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), default="MARKET")
    product_type: Mapped[str] = mapped_column(String(8), default="I")

    # Prices
    entry_price: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    exit_price: Mapped[float | None] = mapped_column(Numeric(18, 6))
    stop_loss: Mapped[float | None] = mapped_column(Numeric(18, 6))
    target: Mapped[float | None] = mapped_column(Numeric(18, 6))

    # P&L
    pnl: Mapped[float | None] = mapped_column(Numeric(18, 6))
    pnl_pct: Mapped[float | None] = mapped_column(Numeric(10, 6))

    # Execution
    broker_type: Mapped[str] = mapped_column(String(32), default="")
    broker_order_id: Mapped[str] = mapped_column(String(64), default="")
    exchange_order_id: Mapped[str] = mapped_column(String(64), default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    slippage_pct: Mapped[float] = mapped_column(Numeric(10, 6), default=0.0)

    # Strategy + SEBI Algo ID
    strategy_id: Mapped[str] = mapped_column(String(64), default="")
    strategy_type: Mapped[str] = mapped_column(String(32), default="")
    algo_id: Mapped[str] = mapped_column(String(32), default="")  # Exchange-assigned algo ID
    signal_strength: Mapped[float] = mapped_column(Float, default=0.0)
    signal_confidence: Mapped[float] = mapped_column(Float, default=0.0)

    # AI reasoning (for SEBI audit compliance)
    ai_reasoning: Mapped[str] = mapped_column(Text, default="")
    ai_model_used: Mapped[str] = mapped_column(String(128), default="")

    # Status
    status: Mapped[str] = mapped_column(String(32), default="OPEN")  # OPEN, CLOSED, CANCELLED
    exit_reason: Mapped[str] = mapped_column(String(64), default="")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationship
    user: Mapped[User] = relationship(back_populates="trades")

    def __repr__(self) -> str:
        return f"<Trade {self.symbol} {self.side} qty={self.quantity} status={self.status}>"


# ── AI Decision Log ──────────────────────────────────────────────────────────


class AIDecisionLog(Base):
    """Every AI/LLM decision recorded for SEBI 5-year audit trail.

    Captures the full reasoning chain: prompt → response → action taken.
    This is the primary compliance artifact for algorithmic trading.
    """

    __tablename__ = "ai_decision_log"
    __table_args__ = (
        Index("ix_ai_log_user_time", "user_id", "created_at"),
        Index("ix_ai_log_symbol", "symbol"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)

    # Decision
    decision_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # e.g. "SIGNAL_GENERATION", "PARAMETER_OPTIMIZATION", "SENTIMENT_ANALYSIS"
    signal: Mapped[str] = mapped_column(String(8), default="")  # BUY, SELL, HOLD
    confidence: Mapped[float] = mapped_column(Float, default=0.0)

    # AI Model
    model_id: Mapped[str] = mapped_column(String(128), default="")
    prompt_hash: Mapped[str] = mapped_column(String(64), default="")  # SHA256 of prompt

    # Full reasoning chain (JSONB for structured storage)
    input_data: Mapped[dict | None] = mapped_column(JSONB)   # Indicators, market data
    reasoning: Mapped[str] = mapped_column(Text, default="")  # LLM reasoning output
    output_data: Mapped[dict | None] = mapped_column(JSONB)  # Parsed action/params

    # Action taken
    action_taken: Mapped[str] = mapped_column(String(32), default="")
    trade_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    # Latency
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationship
    user: Mapped[User] = relationship(back_populates="ai_decisions")

    def __repr__(self) -> str:
        return f"<AIDecisionLog {self.decision_type} {self.symbol} signal={self.signal}>"


# ── Audit Trail ──────────────────────────────────────────────────────────────


class AuditTrail(Base):
    """Generic audit trail for any user action (SEBI requirement).

    Captures who did what, when, from where.
    Retained for 5 years minimum per SEBI guidelines.
    """

    __tablename__ = "audit_trail"
    __table_args__ = (
        Index("ix_audit_user_time", "user_id", "created_at"),
        Index("ix_audit_action", "action"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    # e.g. "LOGIN", "REGISTER", "TRADE_PLACED", "SETTINGS_CHANGED",
    #      "BROKER_CONNECTED", "KYC_VERIFIED", "CONSENT_GIVEN"

    resource_type: Mapped[str] = mapped_column(String(64), default="")
    resource_id: Mapped[str] = mapped_column(String(128), default="")
    details: Mapped[dict | None] = mapped_column(JSONB)

    ip_address: Mapped[str] = mapped_column(String(45), default="")  # IPv6 max
    user_agent: Mapped[str] = mapped_column(String(512), default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<AuditTrail user={self.user_id} action={self.action}>"


# ── Performance Snapshots ────────────────────────────────────────────────────


class PerformanceSnapshot(Base):
    """Daily performance snapshot per user — P&L, equity, drawdown.

    Used for analytics dashboard and SEBI performance reporting.
    """

    __tablename__ = "performance_snapshots"
    __table_args__ = (
        Index("ix_perf_user_date", "user_id", "snapshot_date"),
        UniqueConstraint("user_id", "snapshot_date", name="uq_user_snapshot_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Portfolio state
    equity: Mapped[float] = mapped_column(Numeric(18, 6), default=0.0)
    cash_balance: Mapped[float] = mapped_column(Numeric(18, 6), default=0.0)
    open_positions_count: Mapped[int] = mapped_column(Integer, default=0)
    open_positions_value: Mapped[float] = mapped_column(Numeric(18, 6), default=0.0)

    # Daily P&L
    realized_pnl: Mapped[float] = mapped_column(Numeric(18, 6), default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Numeric(18, 6), default=0.0)
    total_pnl: Mapped[float] = mapped_column(Numeric(18, 6), default=0.0)

    # Risk metrics
    drawdown_pct: Mapped[float] = mapped_column(Numeric(10, 6), default=0.0)
    peak_equity: Mapped[float] = mapped_column(Numeric(18, 6), default=0.0)
    trades_count: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float] = mapped_column(Numeric(8, 6), default=0.0)

    # Strategy breakdown (JSONB for flexibility)
    strategy_breakdown: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<PerformanceSnapshot user={self.user_id} date={self.snapshot_date}>"
