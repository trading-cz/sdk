"""Transport layer — abstract channel and concrete Kafka implementations.

Layer 0: moves bytes through named channels.
No knowledge of events, models, or serialization.
"""

from tradingcz.transport.protocol import Channel, Message, Transport
from tradingcz.transport.kafka import KafkaChannel, KafkaTransport
from tradingcz.transport.request_reply import RequestReplyClient

__all__ = [
    "Channel",
    "Message",
    "Transport",
    "KafkaChannel",
    "KafkaTransport",
    "RequestReplyClient",
]
