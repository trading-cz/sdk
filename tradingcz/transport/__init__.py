"""Transport layer — Kafka-backed concrete messaging.

Kafka is the permanent transport.  ``KafkaChannel`` and ``KafkaTransport``
are the direct concrete API — no abstract ``Channel``/``Transport`` layer.

Layer stack:
    - ``KafkaChannel`` / ``KafkaTransport`` — raw Kafka I/O (with headers)
    - ``KafkaMessage`` — honest wrapper (offset, partition, headers, key, payload)
    - ``TypedProducer`` / ``TypedConsumer`` — type-safe messaging
    - ``TopicRegistry`` — topic naming, config, and header factories
    - ``partition_for()`` — Murmur2-based partition discovery (``transport.hash``)
"""

from tradingcz.transport.kafka_message import KafkaMessage
from tradingcz.transport.kafka import KafkaChannel, KafkaTransport, TopicConfig, TopicRegistry
from tradingcz.transport.stream import TypedConsumer, TypedProducer

__all__ = [
    "KafkaChannel",
    "KafkaMessage",
    "KafkaTransport",
    "TopicConfig",
    "TopicRegistry",
    "TypedConsumer",
    "TypedProducer",
]
