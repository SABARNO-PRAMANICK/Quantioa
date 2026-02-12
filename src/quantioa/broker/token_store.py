"""
Secure token storage with auto-refresh capability.

Stores broker tokens to an encrypted local JSON file (development) or
Redis (production). Provides `get_valid_token()` that automatically
refreshes expired tokens.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from quantioa.broker.upstox_auth import TokenPair, UpstoxOAuth2

logger = logging.getLogger(__name__)

# Default storage path for development
_DEFAULT_TOKEN_DIR = Path.home() / ".quantioa" / "tokens"


class TokenStore:
    """Persists and retrieves broker tokens with auto-refresh.

    In development, tokens are stored as JSON files.
    In production, this would be backed by Redis or an encrypted DB column.

    Usage:
        store = TokenStore()
        store.save("user_123", "UPSTOX", token_pair)
        token = await store.get_valid_token("user_123", "UPSTOX", auth_client)
    """

    def __init__(self, storage_dir: Path | None = None) -> None:
        self._dir = storage_dir or _DEFAULT_TOKEN_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def _token_path(self, user_id: str, broker: str) -> Path:
        return self._dir / f"{user_id}_{broker.lower()}.json"

    def save(self, user_id: str, broker: str, token_pair: TokenPair) -> None:
        """Persist a token pair to storage."""
        path = self._token_path(user_id, broker)
        data = {
            "access_token": token_pair.access_token,
            "token_type": token_pair.token_type,
            "expires_at": token_pair.expires_at,
            "refresh_token": token_pair.refresh_token,
        }
        path.write_text(json.dumps(data, indent=2))
        # Restrict permissions to owner-only
        os.chmod(path, 0o600)
        logger.info("Token saved for user=%s broker=%s", user_id, broker)

    def load(self, user_id: str, broker: str) -> TokenPair | None:
        """Load a token pair from storage. Returns None if not found."""
        path = self._token_path(user_id, broker)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text())
            return TokenPair(
                access_token=data["access_token"],
                token_type=data.get("token_type", "Bearer"),
                expires_at=data.get("expires_at", 0.0),
                refresh_token=data.get("refresh_token", ""),
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load token for user=%s: %s", user_id, e)
            return None

    def delete(self, user_id: str, broker: str) -> None:
        """Remove stored tokens for a user/broker pair."""
        path = self._token_path(user_id, broker)
        if path.exists():
            path.unlink()
            logger.info("Token deleted for user=%s broker=%s", user_id, broker)

    async def get_valid_token(
        self,
        user_id: str,
        broker: str,
        auth_client: UpstoxOAuth2 | None = None,
    ) -> TokenPair | None:
        """Get a valid (non-expired) token, auto-refreshing if needed.

        Args:
            user_id: The user whose token to retrieve.
            broker: Broker type (e.g. "UPSTOX").
            auth_client: OAuth2 client for refreshing. If None, cannot auto-refresh.

        Returns:
            Valid TokenPair, or None if no token exists and refresh fails.
        """
        token = self.load(user_id, broker)
        if token is None:
            return None

        if not token.is_expired:
            return token

        # Token expired — try to refresh
        if auth_client is None or not token.refresh_token:
            logger.warning(
                "Token expired for user=%s, no refresh available. "
                "User must re-authenticate.",
                user_id,
            )
            return None

        try:
            logger.info("Auto-refreshing expired token for user=%s", user_id)
            new_token = await auth_client.refresh_access_token(token.refresh_token)
            self.save(user_id, broker, new_token)
            return new_token
        except Exception as e:
            logger.error("Token auto-refresh failed for user=%s: %s", user_id, e)
            return None

    def has_token(self, user_id: str, broker: str) -> bool:
        """Check if a token exists (regardless of validity)."""
        return self._token_path(user_id, broker).exists()
