"""
Immutable, append-only audit trail logger.

Logs every user action to the ``audit_trail`` table for SEBI 5-year
retention compliance.  Designed to be called from FastAPI middleware
or from individual endpoint handlers.

Usage::

    from quantioa.compliance.audit_log import AuditLogger

    logger = AuditLogger()
    await logger.log(
        db=session,
        user_id=user.id,
        action="TRADE_PLACED",
        resource_type="trade",
        resource_id=str(trade.id),
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent", ""),
        details={"symbol": "RELIANCE", "side": "LONG", "qty": 10},
    )
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from quantioa.db.crud import AuditTrailRepo

logger = logging.getLogger(__name__)

# ── Standard action constants ─────────────────────────────────────────────────
# Use these instead of raw strings for consistency.

# Auth
ACTION_REGISTER = "REGISTER"
ACTION_LOGIN = "LOGIN"
ACTION_LOGIN_FAILED = "LOGIN_FAILED"
ACTION_LOGOUT = "LOGOUT"
ACTION_TOKEN_REFRESH = "TOKEN_REFRESH"
ACTION_PASSWORD_CHANGE = "PASSWORD_CHANGE"

# Account
ACTION_KYC_SUBMITTED = "KYC_SUBMITTED"
ACTION_KYC_VERIFIED = "KYC_VERIFIED"
ACTION_KYC_REJECTED = "KYC_REJECTED"
ACTION_AI_DISCLOSURE_ACCEPTED = "AI_DISCLOSURE_ACCEPTED"
ACTION_CONSENT_GIVEN = "CONSENT_GIVEN"
ACTION_CONSENT_REVOKED = "CONSENT_REVOKED"
ACTION_SETTINGS_CHANGED = "SETTINGS_CHANGED"

# Broker
ACTION_BROKER_CONNECTED = "BROKER_CONNECTED"
ACTION_BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
ACTION_BROKER_TOKEN_REFRESHED = "BROKER_TOKEN_REFRESHED"

# Trading
ACTION_TRADE_PLACED = "TRADE_PLACED"
ACTION_TRADE_MODIFIED = "TRADE_MODIFIED"
ACTION_TRADE_CANCELLED = "TRADE_CANCELLED"
ACTION_TRADE_CLOSED = "TRADE_CLOSED"
ACTION_STOP_LOSS_HIT = "STOP_LOSS_HIT"

# Compliance
ACTION_KILL_SWITCH_ACTIVATED = "KILL_SWITCH_ACTIVATED"
ACTION_KILL_SWITCH_DEACTIVATED = "KILL_SWITCH_DEACTIVATED"
ACTION_OPS_LIMIT_EXCEEDED = "OPS_LIMIT_EXCEEDED"

# Admin
ACTION_USER_SUSPENDED = "USER_SUSPENDED"
ACTION_USER_REACTIVATED = "USER_REACTIVATED"


class AuditLogger:
    """Immutable audit trail logger — writes to DB and Python logging.

    Thread-safe: each call uses its own DB session transaction.
    Failures are logged but never raised — audit logging must not
    break the primary operation.
    """

    async def log(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        action: str,
        resource_type: str = "",
        resource_id: str = "",
        details: dict | None = None,
        ip_address: str = "",
        user_agent: str = "",
    ) -> None:
        """Append an immutable audit entry.

        Args:
            db: Active async session (committed externally via ``get_db``).
            user_id: The user who performed the action.
            action: One of the ``ACTION_*`` constants above.
            resource_type: The type of resource affected (e.g. "trade", "broker").
            resource_id: The specific resource ID.
            details: Arbitrary JSON-serializable metadata.
            ip_address: Client IP.
            user_agent: Client user agent string.
        """
        try:
            entry = await AuditTrailRepo.log_action(
                db,
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            logger.info(
                "AUDIT: user=%s action=%s resource=%s/%s",
                user_id,
                action,
                resource_type,
                resource_id,
            )
            return entry
        except Exception:
            # Audit logging failures must never crash the primary operation.
            logger.exception(
                "Failed to write audit log: user=%s action=%s", user_id, action
            )


# Singleton for convenience
audit_logger = AuditLogger()
