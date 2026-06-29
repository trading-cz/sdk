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


class ServiceNotReadyError(SdkError):
    """Operation called before the service was started (lifecycle violation).

    Raised when accessing a lazy client or calling an operation before
    :meth:`start()` has completed.  Always indicates a programming error in
    the calling code — fix the call order, don't catch this in production.
    """


class DataError(SdkError):
    """The ingestion service returned an error for a data request.

    Raised by :class:`_DataTransport` when the response to a
    :class:`DataRequest` is a :class:`DataError` event, or when the
    response type does not match the expected request type.
    """


class RegistryError(SdkError):
    """A model class is not registered in the required registry.

    Raised by :class:`EventRegistry.event_type_for` and
    :class:`MarketDataRegistry.data_type_for` when a Pydantic model hasn't
    been decorated with ``@register_event`` or ``@register_market_data``.
    """


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
    "ServiceNotReadyError",
    "DataError",
    "RegistryError",
]
