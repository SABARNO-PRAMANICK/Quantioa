"""
Async SQLAlchemy engine and session factory.

The engine is created lazily on first use to avoid import-time side effects
(e.g. when running tests that don't need a real DB connection).

Usage::

    from quantioa.db import get_db

    @app.get("/items")
    async def list_items(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Item))
        return result.scalars().all()
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from quantioa.config import settings

logger = logging.getLogger(__name__)

# ── Lazy engine creation ─────────────────────────────────────────────────────

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_async_url() -> str:
    """Convert postgresql:// → postgresql+asyncpg://"""
    url = settings.postgres_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def get_engine() -> AsyncEngine:
    """Return the async engine, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            _get_async_url(),
            echo=settings.env.value == "development",
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=1800,  # Recycle connections every 30 min
        )
        logger.info("Database engine created: pool_size=10, max_overflow=20")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the session factory, creating it on first call."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


# ── Public aliases (backward compatible) ─────────────────────────────────────
# These are properties that create on first access.


@property
def engine():
    return get_engine()


@property
def AsyncSessionLocal():
    return get_session_factory()


# ── FastAPI dependency ───────────────────────────────────────────────────────


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an async DB session, auto-commits on success.

    Usage::

        @app.post("/users")
        async def create_user(db: AsyncSession = Depends(get_db)):
            db.add(User(...))
            # auto-committed when handler completes
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Health check ─────────────────────────────────────────────────────────────


async def check_db_health() -> dict:
    """Quick DB connectivity check — use in /health endpoints.

    Returns::

        {"database": "healthy", "latency_ms": 2}
        {"database": "unhealthy", "error": "connection refused"}
    """
    import time

    try:
        eng = get_engine()
        start = time.monotonic()
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency = round((time.monotonic() - start) * 1000, 1)
        return {"database": "healthy", "latency_ms": latency}
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
        return {"database": "unhealthy", "error": str(exc)}
