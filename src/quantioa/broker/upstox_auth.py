"""
Upstox OAuth2 authentication flow.

Handles:
- Authorization URL generation
- Code → token exchange
- Token refresh (Upstox tokens expire daily at 3:30 AM IST)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from quantioa.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TokenPair:
    """Access + refresh token with expiry metadata."""

    access_token: str
    token_type: str = "Bearer"
    expires_at: float = 0.0  # Unix timestamp
    refresh_token: str = ""

    @property
    def is_expired(self) -> bool:
        # Add 5-minute buffer before actual expiry
        return time.time() >= (self.expires_at - 300)


class UpstoxOAuth2:
    """Manages the Upstox OAuth2 flow.

    Usage:
        auth = UpstoxOAuth2()

        # Step 1: Redirect user to authorization URL
        url = auth.get_authorization_url()

        # Step 2: After redirect, exchange code for tokens
        tokens = await auth.exchange_code(code)

        # Step 3: Refresh when token expires
        tokens = await auth.refresh_access_token(tokens.refresh_token)
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

    def get_authorization_url(self) -> str:
        """Generate the URL to redirect the user for Upstox login.

        Returns the full authorization URL with query parameters.
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{settings.upstox_auth_url}?{query}"

    async def exchange_code(self, authorization_code: str) -> TokenPair:
        """Exchange an authorization code for access + refresh tokens.

        Args:
            authorization_code: The code received from the OAuth2 callback.

        Returns:
            TokenPair with access_token, refresh_token, and expiry.

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
                # Upstox tokens expire daily at 3:30 AM IST (next day).
                # Set expiry to ~22 hours from now as a safe default.
                expires_at=time.time() + (22 * 3600),
                refresh_token=data.get("refresh_token", ""),
            )

            logger.info("Upstox token exchange successful")
            return token_pair

        except httpx.HTTPStatusError as e:
            logger.error("Upstox token exchange failed: %s", e.response.text)
            raise UpstoxAuthError(
                f"Token exchange failed (HTTP {e.response.status_code}): {e.response.text}"
            ) from e
        except Exception as e:
            logger.error("Upstox token exchange error: %s", e)
            raise UpstoxAuthError(f"Token exchange error: {e}") from e

    async def refresh_access_token(self, refresh_token: str) -> TokenPair:
        """Refresh an expired access token.

        Note: Upstox v2 may not support standard refresh_token flow for all
        app types. In that case, users must re-authenticate daily.

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
                expires_at=time.time() + (22 * 3600),
                refresh_token=data.get("refresh_token", refresh_token),
            )

            logger.info("Upstox token refresh successful")
            return token_pair

        except httpx.HTTPStatusError as e:
            logger.error("Upstox token refresh failed: %s", e.response.text)
            raise UpstoxAuthError(
                f"Token refresh failed (HTTP {e.response.status_code}). "
                "User may need to re-authenticate."
            ) from e

    async def close(self) -> None:
        await self._http.aclose()


class UpstoxAuthError(Exception):
    """Raised when Upstox OAuth2 operations fail."""
