"""Kafka transport — concrete Channel, Transport, and topic registry.

All Kafka-specific code lives here.  Kafka is the permanent transport —
no abstract ``Channel``/``Transport`` layer exists.
"""

from tradingcz.transport.kafka.channel import KafkaChannel, KafkaTransport
from tradingcz.transport.kafka.topics import TopicConfig, TopicRegistry

__all__ = [
    "KafkaChannel",
    "KafkaTransport",
    "TopicConfig",
    "TopicRegistry",
]
