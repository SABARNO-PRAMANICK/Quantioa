"""
Broker Factory — creates broker adapters based on configuration.
"""

from __future__ import annotations

from quantioa.broker.base import BrokerAdapter
from quantioa.broker.token_store import TokenStore
from quantioa.broker.upstox_adapter import UpstoxAdapter
from quantioa.broker.zerodha_adapter import ZerodhaAdapter
from quantioa.models.enums import BrokerType


def get_broker_adapter(
    user_id: str,
    broker_type: BrokerType | str,
    token_store: TokenStore,
) -> BrokerAdapter:
    """Create a broker adapter instance.

    Args:
        user_id: The user ID (e.g., database ID or internal ID).
        broker_type: Enum or string (UPSTOX, ZERODHA).
        token_store: Initialized TokenStore instance.

    Returns:
        Instance of BrokerAdapter.

    Raises:
        ValueError: If broker_type is unknown.
    """
    if isinstance(broker_type, str):
        try:
            broker_type = BrokerType(broker_type.upper())
        except ValueError:
            raise ValueError(f"Unknown broker type: {broker_type}")

    if broker_type == BrokerType.UPSTOX:
        return UpstoxAdapter(user_id=user_id, token_store=token_store)
    
    elif broker_type == BrokerType.ZERODHA:
        return ZerodhaAdapter(user_id=user_id, token_store=token_store)

    raise ValueError(f"Unsupported broker type: {broker_type}")
