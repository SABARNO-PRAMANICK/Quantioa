"""
Common broker-related types.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class TokenPair:
    """Access + refresh token with expiry metadata and user profile.
    
    Shared between Upstox and Zerodha adapters.
    """

    access_token: str
    token_type: str = "Bearer"
    expires_at: float = 0.0  # Unix timestamp
    refresh_token: str = ""
    extended_token: str = ""  # Upstox specific
    public_token: str = ""    # Zerodha specific
    user_id: str = ""
    exchanges: list[str] = field(default_factory=list)
    products: list[str] = field(default_factory=list)

    @property
    def is_expired(self) -> bool:
        # Add 5-minute buffer before actual expiry
        return time.time() >= (self.expires_at - 300)
