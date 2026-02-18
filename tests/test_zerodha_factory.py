
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from quantioa.broker.factory import get_broker_adapter
from quantioa.models.enums import BrokerType
from quantioa.broker.zerodha_adapter import ZerodhaAdapter

@pytest.fixture
def mock_token_store():
    store = MagicMock()
    return store

def test_factory_creates_zerodha_adapter(mock_token_store):
    adapter = get_broker_adapter("USER123", "ZERODHA", mock_token_store)
    assert isinstance(adapter, ZerodhaAdapter)
    assert adapter._user_id == "USER123"

def test_factory_creates_zerodha_adapter_from_string(mock_token_store):
    adapter = get_broker_adapter("USER123", "zerodha", mock_token_store)
    assert isinstance(adapter, ZerodhaAdapter)

def test_factory_raises_error_for_unknown(mock_token_store):
    with pytest.raises(ValueError):
        get_broker_adapter("USER123", "UNKNOWN_BROKER", mock_token_store)
