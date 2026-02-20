"""
CRUD repositories for Quantioa database models.

Each repository provides async create/read/update/delete operations
scoped to a user_id for multi-tenant isolation.

Usage::

    from quantioa.db.crud import UserRepo, TradeRepo

    async with AsyncSessionLocal() as db:
        user = await UserRepo.create(db, email="a@b.com", password_hash="...")
        trades = await TradeRepo.list_by_user(db, user.id, limit=50)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from quantioa.db.models import (
    AIDecisionLog,
    AuditTrail,
    BrokerAccount,
    PerformanceSnapshot,
    Trade,
    User,
)


# ── User Repository ──────────────────────────────────────────────────────────


class UserRepo:
    """CRUD operations for the users table."""

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        email: str,
        password_hash: str,
        role: str = "FREE_TRADER",
        full_name: str | None = None,
    ) -> User:
        user = User(
            email=email,
            password_hash=password_hash,
            role=role,
            full_name=full_name,
        )
        db.add(user)
        await db.flush()
        return user

    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
        return await db.get(User, user_id)

    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> User | None:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    @staticmethod
    async def update_last_login(db: AsyncSession, user_id: uuid.UUID) -> None:
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(last_login_at=datetime.now(timezone.utc))
        )

    @staticmethod
    async def update_role(db: AsyncSession, user_id: uuid.UUID, role: str) -> None:
        await db.execute(
            update(User).where(User.id == user_id).values(role=role)
        )

    @staticmethod
    async def set_kyc_verified(
        db: AsyncSession,
        user_id: uuid.UUID,
        pan_number: str,
        full_name: str,
    ) -> None:
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                pan_number=pan_number,
                full_name=full_name,
                kyc_verified_at=datetime.now(timezone.utc),
                is_verified=True,
            )
        )

    @staticmethod
    async def accept_ai_disclosure(db: AsyncSession, user_id: uuid.UUID) -> None:
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                ai_disclosure_accepted=True,
                consent_timestamp=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def count(db: AsyncSession) -> int:
        result = await db.execute(select(func.count()).select_from(User))
        return result.scalar_one()


# ── Broker Account Repository ────────────────────────────────────────────────


class BrokerAccountRepo:
    """CRUD for user broker connections."""

    @staticmethod
    async def upsert(
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        broker_type: str,
        broker_user_id: str = "",
        access_token: str = "",
        refresh_token: str = "",
        token_expires_at: datetime | None = None,
        exchanges: dict | None = None,
    ) -> BrokerAccount:
        """Insert or update a broker account for a user."""
        result = await db.execute(
            select(BrokerAccount).where(
                BrokerAccount.user_id == user_id,
                BrokerAccount.broker_type == broker_type,
            )
        )
        account = result.scalar_one_or_none()

        if account:
            account.broker_user_id = broker_user_id
            account.access_token = access_token
            account.refresh_token = refresh_token
            account.token_expires_at = token_expires_at
            account.exchanges = exchanges
            account.last_refreshed_at = datetime.now(timezone.utc)
        else:
            account = BrokerAccount(
                user_id=user_id,
                broker_type=broker_type,
                broker_user_id=broker_user_id,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expires_at=token_expires_at,
                exchanges=exchanges,
            )
            db.add(account)

        await db.flush()
        return account

    @staticmethod
    async def get_by_user_and_broker(
        db: AsyncSession, user_id: uuid.UUID, broker_type: str
    ) -> BrokerAccount | None:
        result = await db.execute(
            select(BrokerAccount).where(
                BrokerAccount.user_id == user_id,
                BrokerAccount.broker_type == broker_type,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_user(
        db: AsyncSession, user_id: uuid.UUID
    ) -> list[BrokerAccount]:
        result = await db.execute(
            select(BrokerAccount).where(BrokerAccount.user_id == user_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def disconnect(
        db: AsyncSession, user_id: uuid.UUID, broker_type: str
    ) -> None:
        await db.execute(
            delete(BrokerAccount).where(
                BrokerAccount.user_id == user_id,
                BrokerAccount.broker_type == broker_type,
            )
        )


# ── Trade Repository ─────────────────────────────────────────────────────────


class TradeRepo:
    """CRUD for trade records."""

    @staticmethod
    async def create(db: AsyncSession, **kwargs) -> Trade:
        trade = Trade(**kwargs)
        db.add(trade)
        await db.flush()
        return trade

    @staticmethod
    async def get_by_id(db: AsyncSession, trade_id: uuid.UUID) -> Trade | None:
        return await db.get(Trade, trade_id)

    @staticmethod
    async def list_by_user(
        db: AsyncSession,
        user_id: uuid.UUID,
        *,
        symbol: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Trade]:
        stmt = (
            select(Trade)
            .where(Trade.user_id == user_id)
            .order_by(Trade.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if symbol:
            stmt = stmt.where(Trade.symbol == symbol)
        if status:
            stmt = stmt.where(Trade.status == status)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def close_trade(
        db: AsyncSession,
        trade_id: uuid.UUID,
        *,
        exit_price: float,
        pnl: float,
        pnl_pct: float,
        exit_reason: str = "",
    ) -> None:
        await db.execute(
            update(Trade)
            .where(Trade.id == trade_id)
            .values(
                exit_price=exit_price,
                pnl=pnl,
                pnl_pct=pnl_pct,
                exit_reason=exit_reason,
                status="CLOSED",
                closed_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def count_by_user(
        db: AsyncSession, user_id: uuid.UUID, status: str | None = None
    ) -> int:
        stmt = select(func.count()).select_from(Trade).where(Trade.user_id == user_id)
        if status:
            stmt = stmt.where(Trade.status == status)
        result = await db.execute(stmt)
        return result.scalar_one()


# ── AI Decision Log Repository ───────────────────────────────────────────────


class AIDecisionLogRepo:
    """CRUD for AI decision audit trail (SEBI 5-year retention)."""

    @staticmethod
    async def create(db: AsyncSession, **kwargs) -> AIDecisionLog:
        log = AIDecisionLog(**kwargs)
        db.add(log)
        await db.flush()
        return log

    @staticmethod
    async def list_by_user(
        db: AsyncSession,
        user_id: uuid.UUID,
        *,
        symbol: str | None = None,
        decision_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AIDecisionLog]:
        stmt = (
            select(AIDecisionLog)
            .where(AIDecisionLog.user_id == user_id)
            .order_by(AIDecisionLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if symbol:
            stmt = stmt.where(AIDecisionLog.symbol == symbol)
        if decision_type:
            stmt = stmt.where(AIDecisionLog.decision_type == decision_type)
        result = await db.execute(stmt)
        return list(result.scalars().all())


# ── Audit Trail Repository ──────────────────────────────────────────────────


class AuditTrailRepo:
    """CRUD for generic audit trail."""

    @staticmethod
    async def log_action(
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        action: str,
        resource_type: str = "",
        resource_id: str = "",
        details: dict | None = None,
        ip_address: str = "",
        user_agent: str = "",
    ) -> AuditTrail:
        entry = AuditTrail(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(entry)
        await db.flush()
        return entry

    @staticmethod
    async def list_by_user(
        db: AsyncSession,
        user_id: uuid.UUID,
        *,
        action: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditTrail]:
        stmt = (
            select(AuditTrail)
            .where(AuditTrail.user_id == user_id)
            .order_by(AuditTrail.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if action:
            stmt = stmt.where(AuditTrail.action == action)
        result = await db.execute(stmt)
        return list(result.scalars().all())


# ── Performance Snapshot Repository ──────────────────────────────────────────


class PerformanceSnapshotRepo:
    """CRUD for daily performance snapshots."""

    @staticmethod
    async def upsert(
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        snapshot_date: datetime,
        **metrics,
    ) -> PerformanceSnapshot:
        result = await db.execute(
            select(PerformanceSnapshot).where(
                PerformanceSnapshot.user_id == user_id,
                PerformanceSnapshot.snapshot_date == snapshot_date,
            )
        )
        snap = result.scalar_one_or_none()

        if snap:
            for k, v in metrics.items():
                setattr(snap, k, v)
        else:
            snap = PerformanceSnapshot(
                user_id=user_id,
                snapshot_date=snapshot_date,
                **metrics,
            )
            db.add(snap)

        await db.flush()
        return snap

    @staticmethod
    async def get_range(
        db: AsyncSession,
        user_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> list[PerformanceSnapshot]:
        result = await db.execute(
            select(PerformanceSnapshot)
            .where(
                PerformanceSnapshot.user_id == user_id,
                PerformanceSnapshot.snapshot_date >= start_date,
                PerformanceSnapshot.snapshot_date <= end_date,
            )
            .order_by(PerformanceSnapshot.snapshot_date)
        )
        return list(result.scalars().all())
