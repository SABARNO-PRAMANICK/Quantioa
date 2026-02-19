"""
Unit tests for ZerodhaOAuth2 authentication.

Tests: checksum generation, authorization URL, exchange_token, logout.
"""

import hashlib
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from quantioa.broker.zerodha_auth import ZerodhaOAuth2, ZerodhaAuthError


@pytest.fixture
def auth():
    return ZerodhaOAuth2(
        api_key="test_api_key",
        api_secret="test_api_secret",
        redirect_uri="http://localhost/callback",
    )


class TestChecksum:
    def test_generate_checksum(self, auth):
        """SHA-256 of api_key + request_token + api_secret."""
        request_token = "req_tok_123"
        expected = hashlib.sha256(
            "test_api_keyreq_tok_123test_api_secret".encode()
        ).hexdigest()
        assert auth._generate_checksum(request_token) == expected

    def test_checksum_changes_with_token(self, auth):
        c1 = auth._generate_checksum("token_a")
        c2 = auth._generate_checksum("token_b")
        assert c1 != c2


class TestAuthorizationURL:
    def test_url_contains_api_key(self, auth):
        url = auth.get_authorization_url()
        assert "test_api_key" in url
        assert "v=3" in url


class TestExchangeToken:
    @pytest.mark.asyncio
    async def test_exchange_token_success(self, auth):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "access_token": "new_access_token",
                "public_token": "pub_tok",
                "user_id": "AB1234",
                "exchanges": ["NSE", "BSE"],
                "products": ["CNC", "MIS"],
            }
        }

        auth._http = MagicMock()
        auth._http.post = AsyncMock(return_value=mock_resp)

        token = await auth.exchange_token("request_token_123")

        assert token.access_token == "new_access_token"
        assert token.public_token == "pub_tok"
        assert token.user_id == "AB1234"
        assert token.exchanges == ["NSE", "BSE"]
        assert token.token_type == "token"

        # Verify checksum was sent
        call_kwargs = auth._http.post.call_args[1]
        assert "checksum" in call_kwargs["data"]

    @pytest.mark.asyncio
    async def test_exchange_token_http_error(self, auth):
        mock_resp = httpx.Response(403, json={"error": "Invalid request token"})
        mock_resp.request = httpx.Request("POST", "https://api.kite.trade/session/token")

        auth._http = MagicMock()
        auth._http.post = AsyncMock(
            side_effect=httpx.HTTPStatusError("403", request=mock_resp.request, response=mock_resp)
        )

        with pytest.raises(ZerodhaAuthError, match="Token exchange failed"):
            await auth.exchange_token("bad_token")


class TestLogout:
    @pytest.mark.asyncio
    async def test_logout_success(self, auth):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        auth._http = MagicMock()
        auth._http.delete = AsyncMock(return_value=mock_resp)

        result = await auth.logout("access_token_123")
        assert result is True

    @pytest.mark.asyncio
    async def test_logout_failure(self, auth):
        auth._http = MagicMock()
        auth._http.delete = AsyncMock(side_effect=Exception("Network error"))

        result = await auth.logout("access_token_123")
        assert result is False
