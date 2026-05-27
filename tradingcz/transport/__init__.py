"""Transport layer — abstract channel and concrete implementations.

Layer 0: moves bytes through named channels.
No knowledge of events, models, or serialization.

Subpackages:
    - kafka/  — Kafka-specific Channel, Transport, and topic registry
"""

from tradingcz.transport.protocol import Channel, Message, Transport
from tradingcz.transport.kafka import KafkaChannel, KafkaTransport, TopicConfig, TopicRegistry
from tradingcz.transport.request_reply import RequestReplyClient
from tradingcz.transport.stream import TypedConsumer, TypedProducer

__all__ = [
    "Channel",
    "Message",
    "Transport",
    "KafkaChannel",
    "KafkaTransport",
    "TopicConfig",
    "TopicRegistry",
    "RequestReplyClient",
    "TypedConsumer",
    "TypedProducer",
]
