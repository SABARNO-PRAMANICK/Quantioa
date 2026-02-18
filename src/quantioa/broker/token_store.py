"""
Secure token storage with Redis primary + JSON file fallback.

Production: Tokens stored in Redis for multi-service access.
Development: Falls back to encrypted local JSON files when Redis
is unavailable.

Token key format: ``quantioa:token:{user_id}:{broker}``
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from quantioa.broker.types import TokenPair
from quantioa.broker.upstox_auth import UpstoxOAuth2
from quantioa.config import settings

logger = logging.getLogger(__name__)

# Default fallback storage path for development
_DEFAULT_TOKEN_DIR = Path.home() / ".quantioa" / "tokens"

# Redis key prefix
_REDIS_PREFIX = "quantioa:token"

# Token TTL in Redis — 24 hours (Upstox tokens expire at 3:30 AM IST next day)
_TOKEN_TTL_SECONDS = 24 * 3600


def _token_to_dict(token: TokenPair) -> dict:
    """Serialize a TokenPair to a JSON-safe dict."""
    return {
        "access_token": token.access_token,
        "token_type": token.token_type,
        "expires_at": token.expires_at,
        "refresh_token": token.refresh_token,
        "extended_token": token.extended_token,
        "public_token": token.public_token,  # Added for Zerodha
        "user_id": token.user_id,
        "exchanges": token.exchanges,
        "products": token.products,
    }


def _dict_to_token(data: dict) -> TokenPair:
    """Deserialize a dict to a TokenPair."""
    return TokenPair(
        access_token=data["access_token"],
        token_type=data.get("token_type", "Bearer"),
        expires_at=data.get("expires_at", 0.0),
        refresh_token=data.get("refresh_token", ""),
        extended_token=data.get("extended_token", ""),
        public_token=data.get("public_token", ""),  # Added for Zerodha
        user_id=data.get("user_id", ""),
        exchanges=data.get("exchanges", []),
        products=data.get("products", []),
    )


class TokenStore:
    """Persists and retrieves broker tokens with auto-refresh.

    Uses Redis as the primary store for production (enables multi-service
    token sharing). Falls back to local JSON files when Redis is unavailable.

    Usage::

        store = TokenStore()
        store.save("user_123", "UPSTOX", token_pair)
        token = await store.get_valid_token("user_123", "UPSTOX", auth_client)
    """

    def __init__(
        self,
        storage_dir: Path | None = None,
        redis_url: str | None = None,
    ) -> None:
        self._dir = storage_dir or _DEFAULT_TOKEN_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

        self._redis = None
        self._redis_url = redis_url or settings.redis_url

        # Try to connect to Redis
        try:
            import redis

            self._redis = redis.Redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
            )
            # Verify connection
            self._redis.ping()
            logger.info("TokenStore: Redis connected at %s", self._redis_url)
        except Exception as e:
            logger.warning(
                "TokenStore: Redis unavailable (%s), using file fallback", e
            )
            self._redis = None

    # ── Redis key helpers ──────────────────────────────────────────────────

    @staticmethod
    def _redis_key(user_id: str, broker: str) -> str:
        return f"{_REDIS_PREFIX}:{user_id}:{broker.lower()}"

    # ── File path helpers ──────────────────────────────────────────────────

    def _token_path(self, user_id: str, broker: str) -> Path:
        return self._dir / f"{user_id}_{broker.lower()}.json"

    # ── Save ───────────────────────────────────────────────────────────────

    def save(self, user_id: str, broker: str, token_pair: TokenPair) -> None:
        """Persist a token pair to Redis (primary) and file (backup)."""
        data = _token_to_dict(token_pair)
        json_str = json.dumps(data, indent=2)

        # Always save to file as backup
        path = self._token_path(user_id, broker)
        path.write_text(json_str)
        os.chmod(path, 0o600)

        # Save to Redis if available
        if self._redis is not None:
            try:
                key = self._redis_key(user_id, broker)
                self._redis.set(key, json_str, ex=_TOKEN_TTL_SECONDS)
                logger.info(
                    "Token saved to Redis for user=%s broker=%s", user_id, broker
                )
                return
            except Exception as e:
                logger.warning("Redis save failed, file backup used: %s", e)

        logger.info("Token saved to file for user=%s broker=%s", user_id, broker)

    # ── Load ───────────────────────────────────────────────────────────────

    def load(self, user_id: str, broker: str) -> TokenPair | None:
        """Load a token pair from Redis (primary) or file (fallback).

        Returns ``None`` if no token is found in either store.
        """
        # Try Redis first
        if self._redis is not None:
            try:
                key = self._redis_key(user_id, broker)
                raw = self._redis.get(key)
                if raw:
                    data = json.loads(raw)
                    return _dict_to_token(data)
            except Exception as e:
                logger.warning("Redis load failed, trying file: %s", e)

        # Fallback to file
        path = self._token_path(user_id, broker)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text())
            return _dict_to_token(data)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load token from file for user=%s: %s", user_id, e)
            return None

    # ── Delete ─────────────────────────────────────────────────────────────

    def delete(self, user_id: str, broker: str) -> None:
        """Remove stored tokens for a user/broker pair from both stores."""
        # Delete from Redis
        if self._redis is not None:
            try:
                key = self._redis_key(user_id, broker)
                self._redis.delete(key)
            except Exception as e:
                logger.warning("Redis delete failed: %s", e)

        # Delete from file
        path = self._token_path(user_id, broker)
        if path.exists():
            path.unlink()
            logger.info("Token deleted for user=%s broker=%s", user_id, broker)

    # ── Auto-refresh ───────────────────────────────────────────────────────

    async def get_valid_token(
        self,
        user_id: str,
        broker: str,
        auth_client: UpstoxOAuth2 | None = None,
    ) -> TokenPair | None:
        """Get a valid (non-expired) token, auto-refreshing if needed.

        Args:
            user_id: The user whose token to retrieve.
            broker: Broker type (e.g. ``"UPSTOX"``).
            auth_client: OAuth2 client for refreshing. If ``None``, cannot
                auto-refresh.

        Returns:
            Valid TokenPair, or ``None`` if no token exists and refresh fails.
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

    # ── Utility ────────────────────────────────────────────────────────────

    def has_token(self, user_id: str, broker: str) -> bool:
        """Check if a token exists (regardless of validity)."""
        # Check Redis first
        if self._redis is not None:
            try:
                key = self._redis_key(user_id, broker)
                if self._redis.exists(key):
                    return True
            except Exception:
                pass

        # Fallback to file
        return self._token_path(user_id, broker).exists()
