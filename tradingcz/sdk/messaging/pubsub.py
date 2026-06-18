"""Typed publish/subscribe — TypedProducer, TypedConsumer, TypedParser over KafkaChannel."""

import logging
import os
from collections.abc import AsyncIterator, Callable
from typing import Any

from pydantic import BaseModel

from tradingcz.sdk.serialization import JsonSerializer
from tradingcz.sdk.serialization.protocol import Deserializer, Serializer
from tradingcz.sdk.transport.channel import KafkaChannel
from tradingcz.sdk.transport.message import KafkaMessage
from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.models.headers import DataHeaders, Header
from tradingcz.sdk.models.market import MarketItem, market_item_message_type

logger = logging.getLogger(__name__)


class TypedProducer[T]:
    """Publish typed values via a KafkaChannel.

    Generic in ``T``.  Uses ``Serializer[T]`` + required ``headers_fn``.

    Lifecycle::

        producer = stream_producer(channel, source_app="ingestion")
        await producer.send(item)
        await producer.flush()  # guarantee delivery
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        channel: KafkaChannel,
        serializer: Serializer[T],
        *,
        headers_fn: Callable[[T], dict[str, str]],
        key_fn: Callable[[T], str] | None = None,
    ) -> None:
        self._channel = channel
        self._serializer = serializer
        self._key_fn: Callable[[T], str] = key_fn or (lambda _: "")
        self._headers_fn = headers_fn

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

    async def __aenter__(self) -> "TypedProducer[T]":
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
                logger.debug( "Skipping message on %s — not a valid %s (offset=%d key=%r)", self._channel.name, type(self._deserializer).__name__, msg.offset, msg.key, )

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
                logger.debug( "Skipping message on %s — not a valid %s (offset=%d key=%r)", self._channel.name, type(self._deserializer).__name__, msg.offset, msg.key, )


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
            msg_type = msg.headers.get(Header.EVENT_TYPE, "")
            if not msg_type:
                logger.debug( "Skipping message on %s — no message_type header (offset=%d key=%r)", self._channel.name, msg.offset, msg.key, )
                continue
            model_type = self._types.get(msg_type)
            if model_type is None:
                continue
            try:
                parsed = model_type.model_validate_json(msg.payload)
            except Exception:  # pylint: disable=broad-exception-caught
                logger.debug( "Skipping message on %s — %s failed validation for %s (offset=%d key=%r)", self._channel.name, model_type.__name__, msg_type, msg.offset, msg.key, )
                continue
            yield msg_type, parsed, msg


# ═════════════════════════════════════════════════════════════════════════════
# Pre-configured producer factories
# ═════════════════════════════════════════════════════════════════════════════


def make_market_headers(
    *,
    source_app: str,
    source: str | None = None,
    broker: str | None = None,
) -> Callable[[Any], dict[str, str]]:
    """Return a ``headers_fn`` for ``TypedProducer`` on market data channels.

    The returned callable auto-infers ``event_type`` from the item's
    class name (via :func:`market_item_message_type`) and fills in
    ``source_app``, ``source``, ``broker``, and ``symbol``.

    Args:
        source_app: Service identifier (e.g. ``"ingestion"``, ``"executor"``).
            Becomes the ``Header.SOURCE_APP`` value in every message.
        source: Optional source label.  Defaults to *source_app*.
            Becomes the ``Header.SOURCE`` value.
        broker: Broker identifier (e.g. ``"alpaca"``).  Defaults to
            the ``SDK_BROKER`` environment variable, or ``""``.

    Returns:
        A callable ``(item) → dict[str, str]`` suitable for
        ``TypedProducer(headers_fn=...)``.
    """
    _source = source or source_app
    _broker = broker or os.environ.get("SDK_BROKER", "")

    def _headers(item: Any) -> dict[str, str]:
        msg_type = market_item_message_type(item)
        return DataHeaders(
            event_type=msg_type,
            source_app=source_app,
            source=_source,
            broker=_broker,
            symbol=item.symbol,
        ).to_kafka()

    return _headers


def stream_producer(
    channel: KafkaChannel,
    *,
    source_app: str,
    broker: str | None = None,
) -> TypedProducer[MarketItem]:
    """Create a ``TypedProducer`` pre-configured for market data streaming.

    One-liner that bundles the common stream-publishing pattern.

    **Long-lived** (stream handler keeps producer for its lifetime)::

        producer = stream_producer(channel, source_app="ingestion", broker="alpaca")
        for item in items:
            await producer.send(item)   # JSON, per-symbol key, auto-headers
        await producer.flush()          # guarantee delivery before shutdown

    **Scoped** (auto-flush on exit)::

        async with stream_producer(channel, source_app="ingestion") as producer:
            for item in items:
                await producer.send(item)
        # flush() called automatically

    Use this for high-throughput market data channels (bars, trades,
    quotes, snapshots).  For control-plane event publishing, use
    ``ServiceApp.publish()`` instead — stateless, no cleanup needed.

    Performance tuning goes through environment variables — no code
    changes needed::

        KAFKA_PRODUCER_OVERRIDES='{"linger.ms": "5", "compression.type": "snappy"}'
    """
    return TypedProducer(
        channel=channel,
        serializer=JsonSerializer(),
        key_fn=lambda item: item.symbol,  # type: ignore[union-attr]
        headers_fn=make_market_headers(source_app=source_app, broker=broker),
    )


__all__ = [
    "TypedProducer",
    "TypedConsumer",
    "TypedParser",
    "make_market_headers",
    "stream_producer",
]

