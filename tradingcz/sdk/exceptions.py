"""Shared error types for the trading SDK."""


class SdkError(Exception):
    """Base for all SDK-raised exceptions."""


class TransportError(SdkError):
    """Transport-level failure (connection, timeout, broker unreachable)."""


class TransportConnectionError(TransportError):
    """Cannot connect to the transport backend."""


class TransportTimeoutError(TransportError):
    """Operation timed out at the transport level."""


class SerializationError(SdkError):
    """Serialization or deserialization failed."""


class ConfigurationError(SdkError):
    """Invalid SDK configuration."""


class TopicNotFoundError(TransportError):
    """The requested topic does not exist on the broker."""


class MessageTypeError(SdkError):
    """Received a message of an unexpected type."""


class KafkaConsumerError(SdkError):
    """Kafka consumer-level error reported by librdkafka (corrupt message, etc.)."""


__all__ = [
    "SdkError",
    "TransportError",
    "TransportConnectionError",
    "TransportTimeoutError",
    "SerializationError",
    "ConfigurationError",
    "TopicNotFoundError",
    "MessageTypeError",
    "KafkaConsumerError",
]
