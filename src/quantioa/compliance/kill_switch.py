"""
Emergency kill switch for halting algorithmic trading.

Operates at three levels:
1. **Global** — halts ALL trading on the platform
2. **Per-user** — halts all trading for a specific user
3. **Per-algo** — halts a specific algorithm (via AlgoRegistry)

Kill switch state is stored in-memory for zero-latency reads.
In production, this should also persist to Redis for multi-instance
coordination.

Usage::

    from quantioa.compliance.kill_switch import KillSwitch

    ks = KillSwitch()

    # Global halt (circuit breaker, system failure, etc.)
    ks.activate_global(reason="Market circuit breaker hit")
    assert ks.is_trading_halted()  # True

    # Per-user halt (compliance issue, breach of limits)
    ks.activate_user(user_id, reason="Daily loss limit exceeded")
    assert ks.is_trading_halted(user_id=user_id)  # True

    # Resume
    ks.deactivate_user(user_id)
    ks.deactivate_global()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class HaltRecord:
    """Details of an active halt."""

    reason: str
    activated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    activated_by: str = "system"  # Who triggered it


class KillSwitch:
    """Emergency trading halt — zero-latency in-memory state.

    Usage is deliberately simple: check ``is_trading_halted()`` before
    placing ANY order. The check is O(1) dict lookups.
    """

    def __init__(self) -> None:
        self._global_halt: HaltRecord | None = None
        self._user_halts: dict[str, HaltRecord] = {}
        self._algo_halts: dict[str, HaltRecord] = {}

    # ── Global ────────────────────────────────────────────────────────────

    def activate_global(
        self, *, reason: str = "Emergency halt", activated_by: str = "system"
    ) -> None:
        """Halt ALL trading on the platform."""
        self._global_halt = HaltRecord(
            reason=reason, activated_by=activated_by
        )
        logger.critical(
            "KILL SWITCH: GLOBAL HALT ACTIVATED — reason=%s by=%s",
            reason,
            activated_by,
        )

    def deactivate_global(self) -> None:
        """Resume platform trading."""
        if self._global_halt:
            logger.warning(
                "KILL SWITCH: Global halt DEACTIVATED (was: %s)",
                self._global_halt.reason,
            )
            self._global_halt = None

    # ── Per-user ──────────────────────────────────────────────────────────

    def activate_user(
        self,
        user_id: str,
        *,
        reason: str = "User trading halted",
        activated_by: str = "system",
    ) -> None:
        """Halt trading for a specific user."""
        self._user_halts[str(user_id)] = HaltRecord(
            reason=reason, activated_by=activated_by
        )
        logger.warning(
            "KILL SWITCH: User halt ACTIVATED — user=%s reason=%s",
            user_id,
            reason,
        )

    def deactivate_user(self, user_id: str) -> None:
        """Resume trading for a specific user."""
        key = str(user_id)
        if key in self._user_halts:
            logger.info("KILL SWITCH: User halt DEACTIVATED — user=%s", user_id)
            del self._user_halts[key]

    # ── Per-algo ──────────────────────────────────────────────────────────

    def activate_algo(
        self,
        strategy_id: str,
        *,
        reason: str = "Algo suspended",
        activated_by: str = "system",
    ) -> None:
        """Halt a specific algo/strategy."""
        self._algo_halts[strategy_id] = HaltRecord(
            reason=reason, activated_by=activated_by
        )
        logger.warning(
            "KILL SWITCH: Algo halt ACTIVATED — strategy=%s reason=%s",
            strategy_id,
            reason,
        )

    def deactivate_algo(self, strategy_id: str) -> None:
        """Resume a specific algo/strategy."""
        if strategy_id in self._algo_halts:
            logger.info(
                "KILL SWITCH: Algo halt DEACTIVATED — strategy=%s", strategy_id
            )
            del self._algo_halts[strategy_id]

    # ── Query ─────────────────────────────────────────────────────────────

    def is_trading_halted(
        self,
        *,
        user_id: str | None = None,
        strategy_id: str | None = None,
    ) -> bool:
        """Check if trading is halted at any level.

        Checks in order: global → user → algo.
        Returns True if ANY halt is active.
        """
        if self._global_halt:
            return True
        if user_id and str(user_id) in self._user_halts:
            return True
        if strategy_id and strategy_id in self._algo_halts:
            return True
        return False

    def get_halt_reason(
        self,
        *,
        user_id: str | None = None,
        strategy_id: str | None = None,
    ) -> str | None:
        """Return the reason for the active halt, or None if not halted."""
        if self._global_halt:
            return f"GLOBAL: {self._global_halt.reason}"
        if user_id:
            halt = self._user_halts.get(str(user_id))
            if halt:
                return f"USER: {halt.reason}"
        if strategy_id:
            halt = self._algo_halts.get(strategy_id)
            if halt:
                return f"ALGO: {halt.reason}"
        return None

    def status(self) -> dict:
        """Return full kill switch status for monitoring dashboards."""
        return {
            "global_halt": bool(self._global_halt),
            "global_reason": self._global_halt.reason if self._global_halt else None,
            "user_halts": {
                uid: halt.reason for uid, halt in self._user_halts.items()
            },
            "algo_halts": {
                sid: halt.reason for sid, halt in self._algo_halts.items()
            },
            "total_halts": (
                (1 if self._global_halt else 0)
                + len(self._user_halts)
                + len(self._algo_halts)
            ),
        }


# Singleton
kill_switch = KillSwitch()
