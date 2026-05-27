"""Receiver-side transport — used by strategy pods to request data.

Provides a request/response pattern over the shared events topic,
plus ephemeral data-topic consumption for receiving market data.
"""

from tradingcz.receiver.kafka_aio import AioKafkaReceiverTransport
from tradingcz.receiver.kafka_confluent import ConfluenceKafkaReceiverTransport

__all__ = [
    "AioKafkaReceiverTransport",  # Legacy: aiokafka-based
    "ConfluenceKafkaReceiverTransport",  # New: confluent-kafka-based
]
