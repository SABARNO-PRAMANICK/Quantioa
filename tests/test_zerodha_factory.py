"""
Unit tests for the broker factory.

Tests: Zerodha creation, Upstox creation, string/enum-based, unknown broker.
"""

import pytest
from unittest.mock import MagicMock

from quantioa.broker.factory import get_broker_adapter
from quantioa.broker.zerodha_adapter import ZerodhaAdapter
from quantioa.broker.upstox_adapter import UpstoxAdapter


@pytest.fixture
def mock_token_store():
    return MagicMock()


class TestBrokerFactory:
    def test_creates_zerodha_adapter(self, mock_token_store):
        adapter = get_broker_adapter("USER123", "ZERODHA", mock_token_store)
        assert isinstance(adapter, ZerodhaAdapter)
        assert adapter._user_id == "USER123"

    def test_creates_zerodha_case_insensitive(self, mock_token_store):
        adapter = get_broker_adapter("USER123", "zerodha", mock_token_store)
        assert isinstance(adapter, ZerodhaAdapter)

    def test_creates_upstox_adapter(self, mock_token_store):
        adapter = get_broker_adapter("USER123", "UPSTOX", mock_token_store)
        assert isinstance(adapter, UpstoxAdapter)

    def test_creates_upstox_case_insensitive(self, mock_token_store):
        adapter = get_broker_adapter("USER123", "upstox", mock_token_store)
        assert isinstance(adapter, UpstoxAdapter)

    def test_raises_for_unknown_broker(self, mock_token_store):
        with pytest.raises(ValueError, match="Unknown"):
            get_broker_adapter("USER123", "UNKNOWN_BROKER", mock_token_store)
