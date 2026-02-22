"""
Low-latency AIOKafka publisher for market data.
"""

import json
import logging
from typing import Any
from aiokafka import AIOKafkaProducer

from quantioa.config import settings

logger = logging.getLogger(__name__)


class MarketDataPublisher:
    """Publishes market data ticks to Kafka with low latency."""

    def __init__(self, topic: str = "market_data"):
        self.topic = topic
        self._producer: AIOKafkaProducer | None = None
        # We use acks=1 for speed vs reliability tradeoff
        self._acks = 1 

    async def connect(self) -> None:
        """Initialize the Kafka producer connection."""
        try:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers.split(","),
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks=self._acks,
                client_id="quantioa-data-publisher",
            )
            await self._producer.start()
            logger.info("MarketDataPublisher connected to %s", settings.kafka_bootstrap_servers)
        except Exception as e:
            logger.error("Failed to connect MarketDataPublisher: %s", e)
            raise

    async def publish_tick(self, tick_data: dict[str, Any]) -> None:
        """
        Publish a tick dictionary to Kafka.
        """
        if not self._producer:
            logger.error("Cannot publish: Publisher not connected.")
            return

        try:
            # We don't await the result here for lower latency broadcast
            # A fire-and-forget or batched approach is optimal for high frequency
            await self._producer.send(self.topic, value=tick_data)
        except Exception as e:
            logger.error("Error publishing tick: %s", e)

    async def close(self) -> None:
        """Close the Kafka producer connection."""
        if self._producer:
            await self._producer.stop()
            logger.info("MarketDataPublisher disconnected.")

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
