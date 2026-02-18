import pytest
import os
from unittest.mock import MagicMock, AsyncMock, patch
from dotenv import load_dotenv

# Load env vars from .env file
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from quantioa.services.sentiment.service import SentimentService
from quantioa.services.sentiment.cache import SentimentCache

@pytest.fixture
def mock_cache():
    cache = MagicMock(spec=SentimentCache)
    cache.get = AsyncMock(return_value=None)
    cache.store = AsyncMock()
    return cache

@pytest.mark.asyncio
async def test_sentiment_service_live_integration(mock_cache):
    """
    Integration test for SentimentService using actual OpenRouter API if key is present.
    If not, it should skip or mock.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    # Check if key is set and not the placeholder
    if not api_key or "your_" in api_key or "sk-or-v1" not in api_key:
        pytest.skip("OPENROUTER_API_KEY not set or invalid")

    service = SentimentService(cache=mock_cache)
    
    symbol = "NIFTY50"
    try:
        success = await service.refresh_symbol(symbol)
        assert success is True
        
        # Verify strict structure of what was saved to cache
        # The service calls cache.store(symbol, dict_data)
        mock_cache.store.assert_called_once()
        args, _ = mock_cache.store.call_args
        sentiment_data = args[1]
        
        assert isinstance(sentiment_data, dict)
        assert sentiment_data["score"] >= -1.0 and sentiment_data["score"] <= 1.0
        assert sentiment_data["confidence"] > 0.0
        assert len(sentiment_data["summary"]) > 0
        assert sentiment_data.get("source") == "perplexity_sonar_pro"

    except Exception as e:
        # Check for OpenAI/OpenRouter API errors
        error_str = str(e)
        if "402" in error_str or "credits" in error_str.lower():
            pytest.skip(f"OpenRouter API insufficient credits: {error_str}")
        else:
            raise e

@pytest.mark.asyncio
async def test_sentiment_parsing_mock():
    """Test that the service correctly parses a mock LLM response."""
    mock_response = {
        "choices": [
            {
                "message": {
                    "content": """
                    {
                        "score": 0.75,
                        "confidence": 0.9,
                        "summary": "Market is bullish due to positive earnings.",
                        "headlines": [
                            {"title": "Stock hits all time high", "url": "http://news.com/1", "source": "News"}
                        ]
                    }
                    """
                }
            }
        ]
    }
    
    with patch("quantioa.llm.client.AsyncOpenAI") as MockClient:
        # Mock the client instance and its completions.create method
        client_instance = MockClient.return_value
        client_instance.chat.completions.create = AsyncMock(return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content=mock_response["choices"][0]["message"]["content"]))]
        ))
        
        cache = MagicMock(spec=SentimentCache)
        cache.store = AsyncMock()
        
        service = SentimentService(cache=cache)
        success = await service.refresh_symbol("RELIANCE")
        
        assert success is True
        
        # Verify parsed data
        cache.store.assert_called_once()
        args, _ = cache.store.call_args
        sentiment = args[1]
        
        assert sentiment["score"] == 0.75
        assert sentiment["confidence"] == 0.9
        assert sentiment["summary"] == "Market is bullish due to positive earnings."
        assert len(sentiment["headlines"]) == 1
