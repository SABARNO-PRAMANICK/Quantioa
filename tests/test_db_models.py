"""
Tests for database models and CRUD repositories.

Uses SQLite in-memory for fast testing without Postgres.
JSONB columns are compiled as JSON for SQLite compatibility.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import JSON, create_engine, event, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from quantioa.db.base import Base
from quantioa.db.models import (
    AIDecisionLog,
    AuditTrail,
    BrokerAccount,
    PerformanceSnapshot,
    Trade,
    User,
)

# ── SQLite-compatible engine ──────────────────────────────────────────────────
# Override JSONB → JSON for SQLite (JSONB is Postgres-only)

from sqlalchemy.dialects.postgresql import JSONB

_orig_compile = None


@event.listens_for(Base.metadata, "before_create")
def _patch_jsonb_for_sqlite(target, connection, **kw):
    """Replace JSONB columns with JSON for SQLite tests."""
    if connection.dialect.name == "sqlite":
        for table in target.tables.values():
            for col in table.columns:
                if isinstance(col.type, JSONB):
                    col.type = JSON()


_TEST_ENGINE = create_engine("sqlite:///:memory:", echo=False)
_TestSession = sessionmaker(bind=_TEST_ENGINE)


@pytest.fixture(autouse=True)
def setup_db():
    """Create all tables before each test, drop after."""
    Base.metadata.create_all(_TEST_ENGINE)
    yield
    Base.metadata.drop_all(_TEST_ENGINE)


@pytest.fixture
def db():
    """Provide a transactional test session."""
    session = _TestSession()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# ── Table Structure Tests ────────────────────────────────────────────────────


def test_all_tables_created():
    """Verify all 6 tables exist."""
    inspector = inspect(_TEST_ENGINE)
    tables = inspector.get_table_names()
    assert "users" in tables
    assert "broker_accounts" in tables
    assert "trades" in tables
    assert "ai_decision_log" in tables
    assert "audit_trail" in tables
    assert "performance_snapshots" in tables


def test_user_table_columns():
    inspector = inspect(_TEST_ENGINE)
    columns = {col["name"] for col in inspector.get_columns("users")}
    required = {
        "id", "email", "password_hash", "role", "subscription_tier",
        "is_active", "is_verified", "full_name", "pan_number",
        "kyc_verified_at", "ai_disclosure_accepted", "consent_timestamp",
        "risk_tolerance", "max_daily_loss_pct", "max_weekly_drawdown_pct",
        "created_at", "updated_at", "last_login_at",
    }
    assert required.issubset(columns), f"Missing columns: {required - columns}"


def test_trade_table_columns():
    inspector = inspect(_TEST_ENGINE)
    columns = {col["name"] for col in inspector.get_columns("trades")}
    required = {
        "id", "user_id", "symbol", "side", "quantity",
        "entry_price", "exit_price", "pnl", "pnl_pct",
        "ai_reasoning", "ai_model_used", "status", "exit_reason",
        "broker_order_id", "strategy_id",
    }
    assert required.issubset(columns), f"Missing columns: {required - columns}"


def test_ai_decision_log_columns():
    inspector = inspect(_TEST_ENGINE)
    columns = {col["name"] for col in inspector.get_columns("ai_decision_log")}
    required = {
        "id", "user_id", "symbol", "decision_type",
        "signal", "confidence", "model_id", "reasoning",
        "action_taken", "created_at",
    }
    assert required.issubset(columns), f"Missing columns: {required - columns}"


def test_broker_accounts_unique_constraint():
    """Verify user can only have one account per broker type."""
    inspector = inspect(_TEST_ENGINE)
    unique_constraints = inspector.get_unique_constraints("broker_accounts")
    constraint_columns = [
        tuple(c["column_names"]) for c in unique_constraints
    ]
    assert ("user_id", "broker_type") in constraint_columns


# ── Model CRUD Tests ─────────────────────────────────────────────────────────


def test_create_user(db: Session):
    user = User(
        email="test@quantioa.com",
        password_hash="$2b$12$hashed",
        role="FREE_TRADER",
    )
    db.add(user)
    db.flush()
    assert user.id is not None
    assert user.email == "test@quantioa.com"
    assert user.role == "FREE_TRADER"
    assert user.is_active is True


def test_user_unique_email(db: Session):
    u1 = User(email="unique@test.com", password_hash="hash1")
    u2 = User(email="unique@test.com", password_hash="hash2")
    db.add(u1)
    db.flush()
    db.add(u2)
    with pytest.raises(Exception):  # IntegrityError
        db.flush()


def test_create_broker_account(db: Session):
    user = User(email="broker@test.com", password_hash="hash")
    db.add(user)
    db.flush()

    account = BrokerAccount(
        user_id=user.id,
        broker_type="UPSTOX",
        broker_user_id="UPSTOX123",
        access_token="token",
    )
    db.add(account)
    db.flush()
    assert account.id is not None
    assert account.broker_type == "UPSTOX"


def test_create_trade(db: Session):
    user = User(email="trade@test.com", password_hash="hash")
    db.add(user)
    db.flush()

    trade = Trade(
        user_id=user.id,
        symbol="RELIANCE",
        side="LONG",
        quantity=10,
        entry_price=2500.0,
        status="OPEN",
    )
    db.add(trade)
    db.flush()
    assert trade.id is not None
    assert trade.symbol == "RELIANCE"


def test_create_ai_decision(db: Session):
    user = User(email="ai@test.com", password_hash="hash")
    db.add(user)
    db.flush()

    decision = AIDecisionLog(
        user_id=user.id,
        symbol="TCS",
        decision_type="SIGNAL_GENERATION",
        signal="BUY",
        confidence=0.85,
        model_id="moonshotai/kimi-k2.5",
        reasoning="Strong momentum indicators...",
    )
    db.add(decision)
    db.flush()
    assert decision.id is not None


def test_create_audit_trail(db: Session):
    user = User(email="audit@test.com", password_hash="hash")
    db.add(user)
    db.flush()

    entry = AuditTrail(
        user_id=user.id,
        action="LOGIN",
        ip_address="127.0.0.1",
    )
    db.add(entry)
    db.flush()
    assert entry.id is not None


def test_cascade_delete_user(db: Session):
    """Deleting a user should cascade-delete all related records."""
    user = User(email="cascade@test.com", password_hash="hash")
    db.add(user)
    db.flush()

    trade = Trade(
        user_id=user.id, symbol="INFY", side="LONG",
        quantity=5, entry_price=1500.0,
    )
    account = BrokerAccount(
        user_id=user.id, broker_type="ZERODHA",
    )
    db.add_all([trade, account])
    db.flush()

    assert db.execute(
        select(Trade).where(Trade.user_id == user.id)
    ).scalar_one_or_none() is not None

    db.delete(user)
    db.flush()

    assert db.execute(
        select(Trade).where(Trade.user_id == user.id)
    ).scalar_one_or_none() is None
    assert db.execute(
        select(BrokerAccount).where(BrokerAccount.user_id == user.id)
    ).scalar_one_or_none() is None


def test_user_repr():
    user = User(email="repr@test.com", password_hash="hash", role="PRO_TRADER")
    assert "repr@test.com" in repr(user)
    assert "PRO_TRADER" in repr(user)


def test_trade_repr():
    trade = Trade(
        user_id=uuid.uuid4(), symbol="HDFC", side="SHORT",
        quantity=20, entry_price=1600.0, status="OPEN",
    )
    assert "HDFC" in repr(trade)
    assert "SHORT" in repr(trade)
