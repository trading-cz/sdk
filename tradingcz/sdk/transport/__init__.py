"""Kafka transport primitives."""

from tradingcz.sdk.transport.transport_consumer import TransportConsumer
from tradingcz.sdk.transport.transport_producer import TransportProducer
from tradingcz.sdk.transport.kafka_message import KafkaMessage
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.kafka_header import DataHeader, EventHeader, Header, KafkaHeader
from tradingcz.sdk.transport.kafka_key import KafkaKey
from tradingcz.sdk.transport.kafka_topic import KafkaTopicAdmin, KafkaTopicConfig, KafkaTopicRegistry
from tradingcz.sdk.messaging.fire_and_forget import FireAndForget
from tradingcz.sdk.messaging.request_reply import RequestReply

# Backwards-compatible aliases for code that hasn't migrated from the
# old combined KafkaTransport / KafkaChannel API (removed in L1-L3 refactor).
# These exist only so downstream imports don't crash — the old .channel()
# / .send() / .receive() / .flush() methods are NOT available.
KafkaTransport = TransportProducer  # type: ignore[misc]
KafkaChannel = TransportProducer  # type: ignore[misc]

__all__ = [
    "TransportProducer",
    "TransportConsumer",
    "KafkaTopicAdmin",
    "KafkaTopicConfig",
    "KafkaTopicRegistry",
    "KafkaMessage",
    "KafkaSettings",
    "Header",
    "KafkaHeader",
    "EventHeader",
    "DataHeader",
    "KafkaKey",
    "FireAndForget",
    "RequestReply",
    "KafkaTransport",   # deprecated — use TransportProducer
    "KafkaChannel",     # deprecated — use TransportProducer
]
