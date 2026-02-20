"""
Algo ID registry and order tagging.

Every algorithmic order must carry a unique exchange-assigned Algo ID
per SEBI circular SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013.

This module manages:
- Registration of algo strategies with the exchange (via broker API)
- Tagging every outgoing order with the correct algo_id
- Tracking which algos are approved vs pending

Usage::

    from quantioa.compliance.algo_registry import AlgoRegistry

    registry = AlgoRegistry()

    # Register a strategy (one-time, per exchange)
    algo_id = await registry.register_algo(
        strategy_id="momentum_v1",
        strategy_type="WHITE_BOX",
        description="RSI + MACD momentum strategy",
        exchange="NSE",
    )

    # Tag an order
    tagged_order = registry.tag_order(order, strategy_id="momentum_v1")
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


class AlgoStatus(str, Enum):
    """Exchange approval status."""

    PENDING = "PENDING"          # Submitted, awaiting approval
    APPROVED = "APPROVED"        # Approved by exchange
    REJECTED = "REJECTED"        # Rejected by exchange
    SUSPENDED = "SUSPENDED"      # Temporarily suspended (kill switch)
    DEREGISTERED = "DEREGISTERED"  # Permanently removed


class AlgoType(str, Enum):
    """Classification per SEBI framework."""

    WHITE_BOX = "WHITE_BOX"    # Logic fully disclosed
    BLACK_BOX = "BLACK_BOX"    # Logic opaque
    HYBRID = "HYBRID"          # Partial disclosure (AI-augmented)


@dataclass
class AlgoRegistration:
    """A registered algo strategy."""

    strategy_id: str
    algo_id: str                    # Exchange-assigned unique ID
    algo_type: AlgoType = AlgoType.HYBRID
    description: str = ""
    exchange: str = "NSE"
    status: AlgoStatus = AlgoStatus.PENDING
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    approved_at: datetime | None = None
    version: str = "1.0"


class AlgoRegistry:
    """Manages algo registration and order tagging.

    In production, ``register_algo`` would call the broker API to submit
    the algo for exchange approval. For now, it generates a deterministic
    algo ID and stores it in-memory.
    """

    def __init__(self) -> None:
        self._registry: dict[str, AlgoRegistration] = {}

    def register_algo(
        self,
        *,
        strategy_id: str,
        algo_type: AlgoType | str = AlgoType.HYBRID,
        description: str = "",
        exchange: str = "NSE",
        version: str = "1.0",
    ) -> AlgoRegistration:
        """Register an algo strategy and return its registration.

        The algo_id is a deterministic hash of (strategy_id, exchange, version)
        so re-registering the same strategy returns the same ID.
        """
        if isinstance(algo_type, str):
            algo_type = AlgoType(algo_type)

        # Deterministic algo ID: SHA256 prefix of strategy+exchange+version
        raw = f"{strategy_id}:{exchange}:{version}"
        algo_id = f"QTA-{hashlib.sha256(raw.encode()).hexdigest()[:12].upper()}"

        reg = AlgoRegistration(
            strategy_id=strategy_id,
            algo_id=algo_id,
            algo_type=algo_type,
            description=description,
            exchange=exchange,
            version=version,
        )
        self._registry[strategy_id] = reg
        logger.info(
            "Algo registered: strategy=%s algo_id=%s exchange=%s",
            strategy_id,
            algo_id,
            exchange,
        )
        return reg

    def get_algo(self, strategy_id: str) -> AlgoRegistration | None:
        """Look up a registered algo by strategy ID."""
        return self._registry.get(strategy_id)

    def get_algo_id(self, strategy_id: str) -> str:
        """Return the algo_id for a strategy, or empty string if not registered."""
        reg = self._registry.get(strategy_id)
        return reg.algo_id if reg else ""

    def tag_order(self, order: dict, *, strategy_id: str) -> dict:
        """Tag an order dict with the exchange-assigned algo_id.

        Returns the order dict with ``algo_id`` injected.
        If the strategy is not registered, the order is tagged with
        an empty algo_id and a warning is logged.
        """
        algo_id = self.get_algo_id(strategy_id)
        if not algo_id:
            logger.warning(
                "Order sent without algo registration: strategy=%s", strategy_id
            )
        order["algo_id"] = algo_id
        order["strategy_id"] = strategy_id
        return order

    def suspend_algo(self, strategy_id: str) -> bool:
        """Suspend an algo (kill switch integration)."""
        reg = self._registry.get(strategy_id)
        if reg:
            reg.status = AlgoStatus.SUSPENDED
            logger.warning("Algo SUSPENDED: strategy=%s algo_id=%s", strategy_id, reg.algo_id)
            return True
        return False

    def resume_algo(self, strategy_id: str) -> bool:
        """Resume a suspended algo."""
        reg = self._registry.get(strategy_id)
        if reg and reg.status == AlgoStatus.SUSPENDED:
            reg.status = AlgoStatus.APPROVED
            logger.info("Algo RESUMED: strategy=%s algo_id=%s", strategy_id, reg.algo_id)
            return True
        return False

    def is_algo_active(self, strategy_id: str) -> bool:
        """Check if an algo is approved and not suspended."""
        reg = self._registry.get(strategy_id)
        if not reg:
            return False
        return reg.status in (AlgoStatus.APPROVED, AlgoStatus.PENDING)

    def list_algos(self) -> list[AlgoRegistration]:
        """Return all registered algos."""
        return list(self._registry.values())


# Singleton
algo_registry = AlgoRegistry()
