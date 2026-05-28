"""Typed producer and consumer — typed wrappers over KafkaChannel.

Wraps a byte-level ``KafkaChannel`` with a ``Codec[T]`` to provide
type-safe ``send(T)`` and ``consume() → AsyncIterator[T]``.

Usage::

    channel = await transport.channel("dev-event")
    producer = TypedProducer(
        channel=channel,
        serializer=JsonCodec(TradingSignal),
        source_app="my-strategy",
        key_fn=lambda s: s.symbol,
    )
    await producer.send(signal)
"""

from collections.abc import AsyncIterator, Callable

from tradingcz.model.headers import make_headers
from tradingcz.serialization.protocol import Deserializer, Serializer
from tradingcz.transport.kafka_message import KafkaMessage


def _default_headers_fn[T](source_app: str) -> Callable[[T], dict[str, str]]:
    """Return a headers_fn that auto-infers message_type from the value's class name."""
    def _fn(value: T) -> dict[str, str]:
        return make_headers(
            message_type=type(value).__name__.lower(),
            source_app=source_app,
        )
    return _fn


class TypedProducer[T]:
    """Publish typed values via a KafkaChannel.

    Generic in the message type ``T``.  Uses a ``Serializer[T]`` to
    convert values to bytes.  Optional ``key_fn`` for Kafka partition
    routing.

    Headers are always included — by default, ``message_type`` is
    auto-inferred from the value's class name (e.g. ``TradingSignal``
    → ``"trading_signal"``).  Override via ``headers_fn``.
    """

    def __init__(
        self,
        channel: "KafkaChannel",
        serializer: Serializer[T],
        *,
        source_app: str = "",
        key_fn: Callable[[T], str] | None = None,
        headers_fn: Callable[[T], dict[str, str]] | None = None,
    ) -> None:
        self._channel = channel
        self._serializer = serializer
        self._key_fn: Callable[[T], str] = key_fn or (lambda _: "")
        self._headers_fn: Callable[[T], dict[str, str]] = (
            headers_fn or _default_headers_fn(source_app)
        )

    @property
    def channel(self) -> "KafkaChannel":
        """The underlying Kafka channel."""
        return self._channel

    async def send(self, value: T) -> None:
        """Serialize *value* and publish to the channel.

        Key is computed by ``key_fn(value)`` (default: empty string).
        Headers are always set — by default, ``message_type`` is the
        lowercased class name and ``source_app`` from the constructor.
        """
        payload = self._serializer.serialize(value)
        key = self._key_fn(value)
        headers = self._headers_fn(value)
        await self._channel.send(payload, key=key, headers=headers)


class TypedConsumer[T]:
    """Consume typed values from a KafkaChannel.

    Generic in the message type ``T``.  Uses a ``Deserializer[T]``
    to parse raw bytes into typed models.

    For access to Kafka metadata (key, headers, offset), use
    ``consume_with_metadata()`` instead.
    """

    def __init__(
        self,
        channel: "KafkaChannel",
        deserializer: Deserializer[T],
    ) -> None:
        self._channel = channel
        self._deserializer = deserializer

    @property
    def channel(self) -> "KafkaChannel":
        """The underlying Kafka channel."""
        return self._channel

    async def consume(self) -> AsyncIterator[T]:
        """Yield typed values (strips Kafka metadata).

        Each call creates an independent subscriber (fan-out semantics
        inherited from ``KafkaChannel.receive()``).
        """
        async for msg in self._channel.receive():
            yield self._deserializer.deserialize(msg.payload)

    async def consume_with_metadata(self) -> AsyncIterator[tuple[T, KafkaMessage]]:
        """Yield typed values WITH raw KafkaMessage metadata.

        Use this when you need access to the Kafka message key, headers,
        offset, or partition for deduplication, tracing, or offset
        checkpointing.
        """
        async for msg in self._channel.receive():
            yield self._deserializer.deserialize(msg.payload), msg


class TypedParser:
    """Parse raw Kafka messages into typed models based on ``message_type`` header.

    Unlike ``TypedConsumer`` (which deserializes EVERYTHING as one type),
    ``TypedParser`` reads the ``message_type`` header and dispatches to
    the correct Pydantic model.  This is the primary mechanism for consuming
    from the shared event topic where multiple message types coexist.

    Usage::

        parser = TypedParser(
            channel=events_channel,
            types={"data_request": DataRequest, "data_ready": DataReady},
        )
        async for msg_type, model, raw in parser.parse():
            match msg_type:
                case "data_request": handle_request(model)
                case "data_ready": handle_ready(model)
    """

    def __init__(
        self,
        channel: "KafkaChannel",
        types: dict[str, type],
    ) -> None:
        self._channel = channel
        self._types = types

    async def parse(self) -> AsyncIterator[tuple[str, object, KafkaMessage]]:
        """Yield ``(message_type, parsed_model, raw_message)`` tuples.

        Messages whose ``message_type`` is not in the registered types
        are silently skipped (expected on a shared topic).
        """
        async for msg in self._channel.receive():
            msg_type = msg.headers.get("message_type", "")
            model_type = self._types.get(msg_type)
            if model_type is None:
                continue
            try:
                parsed = model_type.model_validate_json(msg.payload)
            except Exception:
                continue
            yield msg_type, parsed, msg
