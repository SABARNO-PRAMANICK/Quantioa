"""
Upstox OAuth2 authentication flow.

Handles:
- Authorization URL generation
- Code → token exchange (with extended_token + user profile)
- Token refresh (Upstox tokens expire daily at 3:30 AM IST)
- Semi-automated token request (V3 initiator flow)
- Logout (session invalidation)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

from quantioa.config import settings

logger = logging.getLogger(__name__)

# IST timezone offset (+5:30)
_IST = timezone(timedelta(hours=5, minutes=30))


def _next_330am_ist_unix() -> float:
    """Calculate the Unix timestamp for the next 3:30 AM IST.

    Upstox tokens always expire at 3:30 AM IST the next day,
    regardless of when they were generated.
    """
    now_ist = datetime.now(_IST)
    target = now_ist.replace(hour=3, minute=30, second=0, microsecond=0)

    # If we're past 3:30 AM today, expiry is tomorrow at 3:30 AM
    if now_ist >= target:
        target += timedelta(days=1)

    return target.timestamp()


@dataclass
class TokenPair:
    """Access + refresh token with expiry metadata and user profile."""

    access_token: str
    token_type: str = "Bearer"
    expires_at: float = 0.0  # Unix timestamp
    refresh_token: str = ""
    extended_token: str = ""  # Long-lived read-only token
    user_id: str = ""  # Upstox UCC
    exchanges: list[str] = field(default_factory=list)  # e.g. ["NSE", "BSE"]
    products: list[str] = field(default_factory=list)  # e.g. ["I", "D"]

    @property
    def is_expired(self) -> bool:
        # Add 5-minute buffer before actual expiry
        return time.time() >= (self.expires_at - 300)


class UpstoxOAuth2:
    """Manages the Upstox OAuth2 flow.

    Usage::

        auth = UpstoxOAuth2()

        # Step 1: Redirect user to authorization URL
        url = auth.get_authorization_url()

        # Step 2: After redirect, exchange code for tokens
        tokens = await auth.exchange_code(code)

        # Step 3: Refresh when token expires
        tokens = await auth.refresh_access_token(tokens.refresh_token)

        # Alternative: Semi-automated token request (V3)
        result = await auth.request_token()

        # Clean up
        await auth.logout(access_token)
    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
    ) -> None:
        self.client_id = client_id or settings.upstox_api_key
        self.client_secret = client_secret or settings.upstox_api_secret
        self.redirect_uri = redirect_uri or settings.upstox_redirect_uri
        self._http = httpx.AsyncClient(timeout=30.0)

    def get_authorization_url(self, state: str = "") -> str:
        """Generate the URL to redirect the user for Upstox login.

        Args:
            state: Optional state parameter for CSRF protection.

        Returns:
            The full authorization URL with query parameters.
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
        }
        if state:
            params["state"] = state
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{settings.upstox_auth_url}?{query}"

    async def exchange_code(self, authorization_code: str) -> TokenPair:
        """Exchange an authorization code for access + refresh tokens.

        The Upstox token response also includes user profile info
        (user_id, exchanges, products, order_types) which we capture
        in the TokenPair.

        Args:
            authorization_code: The code received from the OAuth2 callback.

        Returns:
            TokenPair with access_token, extended_token, user profile,
            and expiry set to next 3:30 AM IST.

        Raises:
            UpstoxAuthError: If the token exchange fails.
        """
        payload = {
            "code": authorization_code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        }

        try:
            resp = await self._http.post(
                settings.upstox_token_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()

            token_pair = TokenPair(
                access_token=data["access_token"],
                token_type=data.get("token_type", "Bearer"),
                # Upstox tokens expire at 3:30 AM IST next day
                expires_at=_next_330am_ist_unix(),
                refresh_token=data.get("refresh_token", ""),
                extended_token=data.get("extended_token", ""),
                user_id=data.get("user_id", ""),
                exchanges=data.get("exchanges", []),
                products=data.get("products", []),
            )

            logger.info(
                "Upstox token exchange successful for user=%s, "
                "exchanges=%s, products=%s",
                token_pair.user_id,
                token_pair.exchanges,
                token_pair.products,
            )
            return token_pair

        except httpx.HTTPStatusError as e:
            logger.error("Upstox token exchange failed: %s", e.response.text)
            raise UpstoxAuthError(
                f"Token exchange failed (HTTP {e.response.status_code}): "
                f"{e.response.text}"
            ) from e
        except Exception as e:
            logger.error("Upstox token exchange error: %s", e)
            raise UpstoxAuthError(f"Token exchange error: {e}") from e

    async def refresh_access_token(self, refresh_token: str) -> TokenPair:
        """Refresh an expired access token.

        Note: Upstox v2 may not support standard ``refresh_token`` flow
        for all app types. In that case, users must re-authenticate daily.

        Args:
            refresh_token: The refresh token from the original exchange.

        Returns:
            New TokenPair with fresh access_token.
        """
        payload = {
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
        }

        try:
            resp = await self._http.post(
                settings.upstox_token_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()

            token_pair = TokenPair(
                access_token=data["access_token"],
                token_type=data.get("token_type", "Bearer"),
                expires_at=_next_330am_ist_unix(),
                refresh_token=data.get("refresh_token", refresh_token),
                extended_token=data.get("extended_token", ""),
                user_id=data.get("user_id", ""),
                exchanges=data.get("exchanges", []),
                products=data.get("products", []),
            )

            logger.info("Upstox token refresh successful")
            return token_pair

        except httpx.HTTPStatusError as e:
            logger.error("Upstox token refresh failed: %s", e.response.text)
            raise UpstoxAuthError(
                f"Token refresh failed (HTTP {e.response.status_code}). "
                "User may need to re-authenticate."
            ) from e

    async def request_token(self) -> dict:
        """Semi-automated V3 token request flow.

        Sends a token request to the user who must approve it via
        the Upstox app or WhatsApp. On approval, the access token
        is delivered to the configured notifier webhook URL.

        Returns:
            Dict with ``authorization_expiry`` and ``notifier_url``.

        Raises:
            UpstoxAuthError: If the request fails.
        """
        url = (
            f"https://api.upstox.com/v3/login/auth/token/request/"
            f"{self.client_id}"
        )
        payload = {"client_secret": self.client_secret}

        try:
            resp = await self._http.post(
                url,
                json=payload,
                headers={
                    "accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            result = resp.json()

            logger.info(
                "Token request sent. Awaiting user approval. "
                "Expires at: %s",
                result.get("data", {}).get("authorization_expiry"),
            )
            return result.get("data", {})

        except httpx.HTTPStatusError as e:
            logger.error("Token request failed: %s", e.response.text)
            raise UpstoxAuthError(
                f"Token request failed (HTTP {e.response.status_code})"
            ) from e

    async def logout(self, access_token: str) -> bool:
        """Invalidate the current session.

        Args:
            access_token: The token to invalidate.

        Returns:
            ``True`` if logout was successful.
        """
        try:
            resp = await self._http.delete(
                f"{settings.upstox_base_url}/logout",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
            result = resp.json()
            success = result.get("data", False)
            if success:
                logger.info("Upstox session logged out successfully")
            return success

        except Exception as e:
            logger.error("Logout failed: %s", e)
            return False

    async def close(self) -> None:
        await self._http.aclose()


class UpstoxAuthError(Exception):
    """Raised when Upstox OAuth2 operations fail."""
