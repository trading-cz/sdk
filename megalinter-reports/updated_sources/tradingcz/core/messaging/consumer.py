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

import logging
from collections.abc import AsyncIterator, Callable

from pydantic import BaseModel

from tradingcz.core.serialization.protocol import Deserializer, Serializer
from tradingcz.core.transport.kafka import KafkaChannel
from tradingcz.core.transport.message import KafkaMessage
from tradingcz.models.headers import Header, MessageType, make_headers

logger = logging.getLogger(__name__)


def _default_headers_fn[T](source_app: str) -> Callable[[T], dict[str, str]]:
    """Return a headers_fn that auto-infers MessageType from the value's class name.

    Converts CamelCase class name to snake_case and looks up the
    corresponding :class:`MessageType` enum member (e.g. ``TradingSignal``
    → ``MessageType.TRADING_SIGNAL`` → ``\"trading_signal\"``).

    If the class name doesn't match any known MessageType, the caller
    should supply an explicit ``headers_fn`` instead.
    """

    def _fn(value: T) -> dict[str, str]:
        import re

        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", type(value).__name__).lower()
        try:
            mt = MessageType(snake)
        except ValueError:
            raise ValueError(
                f"Cannot infer MessageType from class {type(value).__name__!r}: "
                f"'{snake}' is not a known message_type. "
                f"Supply an explicit 'headers_fn' to TypedProducer."
            ) from None
        return make_headers(
            message_type=mt,
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

    Lifecycle::

        # Long-lived producer (e.g. streaming):
        producer = stream_producer(channel, source_app="ingestion")
        for item in items:
            await producer.send(item)
        await producer.flush()  # guarantee delivery before shutdown

        # Scoped producer (auto-flush on exit):
        async with stream_producer(channel, source_app="ingestion") as producer:
            for item in items:
                await producer.send(item)
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        channel: KafkaChannel,
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
    def channel(self) -> KafkaChannel:
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

    async def flush(self) -> None:
        """Wait for all queued messages to be delivered to Kafka.

        Call before shutdown to guarantee delivery.  For streaming
        producers, call this in your ``close()`` or shutdown handler.
        """
        await self._channel.flush()

    async def __aenter__(self) -> TypedProducer[T]:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.flush()


class TypedConsumer[T]:
    """Consume typed values from a KafkaChannel.

    Generic in the message type ``T``.  Uses a ``Deserializer[T]``
    to parse raw bytes into typed models.

    For access to Kafka metadata (key, headers, offset), use
    ``consume_with_metadata()`` instead.
    """

    def __init__(
        self,
        channel: KafkaChannel,
        deserializer: Deserializer[T],
    ) -> None:
        self._channel = channel
        self._deserializer = deserializer

    @property
    def channel(self) -> KafkaChannel:
        """The underlying Kafka channel."""
        return self._channel

    async def consume(self) -> AsyncIterator[T]:
        """Yield typed values (strips Kafka metadata).

        Each call creates an independent subscriber (fan-out semantics
        inherited from ``KafkaChannel.receive()``).

        Messages that fail to deserialize as ``T`` are logged and
        skipped — the iterator does NOT crash.  On a shared multi-type
        topic this is essential for resilience.
        """
        async for msg in self._channel.receive():
            try:
                yield self._deserializer.deserialize(msg.payload)
            except Exception:  # pylint: disable=broad-exception-caught
                logger.debug(
                    "Skipping message on %s — not a valid %s (offset=%d key=%r)",
                    self._channel.name,
                    type(self._deserializer).__name__,
                    msg.offset,
                    msg.key,
                )

    async def consume_with_metadata(self) -> AsyncIterator[tuple[T, KafkaMessage]]:
        """Yield typed values WITH raw KafkaMessage metadata.

        Use this when you need access to the Kafka message key, headers,
        offset, or partition for deduplication, tracing, or offset
        checkpointing.

        Messages that fail to deserialize as ``T`` are logged and skipped.
        """
        async for msg in self._channel.receive():
            try:
                yield self._deserializer.deserialize(msg.payload), msg
            except Exception:  # pylint: disable=broad-exception-caught
                logger.debug(
                    "Skipping message on %s — not a valid %s (offset=%d key=%r)",
                    self._channel.name,
                    type(self._deserializer).__name__,
                    msg.offset,
                    msg.key,
                )


class TypedParser:
    """Parse raw Kafka messages into typed models based on message_type header.

    Dispatches to the correct Pydantic model for multi-type shared topics.
    Messages with an unrecognized ``message_type`` header are silently skipped.
    """

    def __init__(
        self, channel: KafkaChannel, types: dict[str, type[BaseModel]]
    ) -> None:
        self._channel = channel
        self._types = types

    async def parse(self) -> AsyncIterator[tuple[str, object, KafkaMessage]]:
        """Yield (message_type, parsed_model, raw_message) tuples.

        Messages whose ``message_type`` header is not registered in *types*
        are skipped.  Messages whose payload fails validation against the
        registered model are logged and skipped.
        """
        async for msg in self._channel.receive():
            msg_type = msg.headers.get(Header.MESSAGE_TYPE, "")
            if not msg_type:
                logger.debug(
                    "Skipping message on %s — no message_type header (offset=%d key=%r)",
                    self._channel.name,
                    msg.offset,
                    msg.key,
                )
                continue
            model_type = self._types.get(msg_type)
            if model_type is None:
                continue
            try:
                parsed = model_type.model_validate_json(msg.payload)
            except Exception:  # pylint: disable=broad-exception-caught
                logger.debug(
                    "Skipping message on %s — %s failed validation for %s (offset=%d key=%r)",
                    self._channel.name,
                    model_type.__name__,
                    msg_type,
                    msg.offset,
                    msg.key,
                )
                continue
            yield msg_type, parsed, msg
