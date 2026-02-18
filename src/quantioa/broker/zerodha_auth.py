"""
Zerodha Kite Connect OAuth2 authentication flow.

Handles:
- Authorization URL generation
- Code (request_token) → access_token exchange
- Checksum generation
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from quantioa.broker.types import TokenPair
from quantioa.config import settings

logger = logging.getLogger(__name__)

# IST timezone offset (+5:30)
_IST = timezone(timedelta(hours=5, minutes=30))


def _next_6am_ist_unix() -> float:
    """Calculate the Unix timestamp for the next 6:00 AM IST.

    Zerodha tokens expire at 6:00 AM IST the next day.
    """
    now_ist = datetime.now(_IST)
    target = now_ist.replace(hour=6, minute=0, second=0, microsecond=0)

    # If we're past 6:00 AM today, expiry is tomorrow at 6:00 AM
    if now_ist >= target:
        target += timedelta(days=1)

    return target.timestamp()


class ZerodhaOAuth2:
    """Manages the Zerodha Kite Connect authentication flow.

    Usage::

        auth = ZerodhaOAuth2()
        url = auth.get_authorization_url()
        # User visits URL -> redirects to callback with request_token
        tokens = await auth.exchange_token(request_token)
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        redirect_uri: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.zerodha_api_key
        self.api_secret = api_secret or settings.zerodha_api_secret
        self.redirect_uri = redirect_uri or settings.zerodha_redirect_uri
        self._http = httpx.AsyncClient(timeout=30.0)

    def get_authorization_url(self) -> str:
        """Generate the login URL."""
        return f"{settings.zerodha_auth_url}?api_key={self.api_key}&v=3"

    def _generate_checksum(self, request_token: str) -> str:
        """Generate SHA-256 checksum for token exchange.

        Checksum = SHA256(api_key + request_token + api_secret)
        """
        data = f"{self.api_key}{request_token}{self.api_secret}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    async def exchange_token(self, request_token: str) -> TokenPair:
        """Exchange request_token for access_token.
        
        Using: POST /session/token
        """
        checksum = self._generate_checksum(request_token)
        
        payload = {
            "api_key": self.api_key,
            "request_token": request_token,
            "checksum": checksum,
        }

        try:
            resp = await self._http.post(
                f"{settings.zerodha_base_url}/session/token",
                data=payload,
                headers={"X-Kite-Version": "3"},
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})

            token_pair = TokenPair(
                access_token=data.get("access_token", ""),
                token_type="token",
                expires_at=_next_6am_ist_unix(),
                refresh_token=data.get("refresh_token", ""),
                public_token=data.get("public_token", ""),
                user_id=data.get("user_id", ""),
                exchanges=data.get("exchanges", []),
                products=data.get("products", []),
            )

            logger.info(
                "Zerodha token exchange successful for user=%s",
                token_pair.user_id,
            )
            return token_pair

        except httpx.HTTPStatusError as e:
            logger.error("Zerodha token exchange failed: %s", e.response.text)
            raise ZerodhaAuthError(
                f"Token exchange failed (HTTP {e.response.status_code}): "
                f"{e.response.text}"
            ) from e
        except Exception as e:
            logger.error("Zerodha token exchange error: %s", e)
            raise ZerodhaAuthError(f"Token exchange error: {e}") from e
    
    async def logout(self, access_token: str) -> bool:
        """Invalidate the session."""
        try:
            resp = await self._http.delete(
                f"{settings.zerodha_base_url}/session/token",
                params={"api_key": self.api_key, "access_token": access_token},
                headers={"X-Kite-Version": "3"}
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error("Zerodha logout failed: %s", e)
            return False

    async def close(self) -> None:
        await self._http.aclose()


class ZerodhaAuthError(Exception):
    """Raised when Zerodha authentication fails."""
