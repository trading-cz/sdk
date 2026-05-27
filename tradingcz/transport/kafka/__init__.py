"""Kafka transport implementation — concrete Channel and Transport.

All Kafka-specific code lives here.  The parent ``transport`` package
contains only transport-agnostic abstractions (Channel, Transport,
TypedProducer, RequestReplyClient, etc.).

Exports:
    - KafkaChannel, KafkaTransport — concrete Channel/Transport implementations
    - TopicConfig, TopicRegistry — Kafka topic naming and configuration
"""

from tradingcz.transport.kafka.channel import KafkaChannel, KafkaTransport
from tradingcz.transport.kafka.topics import TopicConfig, TopicRegistry

__all__ = [
    "KafkaChannel",
    "KafkaTransport",
    "TopicConfig",
    "TopicRegistry",
]
