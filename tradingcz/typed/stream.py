"""Typed producer and consumer — generic wrappers over a Channel.

Layer 2 of the transport stack.  Wraps a byte-level ``Channel`` with
a ``Codec[T]`` to provide type-safe ``send(T)`` and ``consume() → AsyncIterator[T]``.

Services compose these for their specific needs::

    channel = await transport.channel("dev.signals")
    producer = TypedProducer(
        channel=channel,
        serializer=JsonCodec(TradingSignal),
        key_fn=lambda s: f"{s.strategy_id}:{s.symbol}",
    )
    await producer.send(signal)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Callable, Generic, TypeVar

from tradingcz.serialization.protocol import Deserializer, Serializer
from tradingcz.transport.protocol import Channel

T = TypeVar("T")


class TypedProducer(Generic[T]):
    """Publish typed values to a channel.

    Generic in the message type ``T``.  Uses a ``Serializer[T]`` to
    convert values to bytes and an optional ``key_fn`` for Kafka
    message keys.
    """

    def __init__(
        self,
        channel: Channel,
        serializer: Serializer[T],
        *,
        key_fn: Callable[[T], str] | None = None,
    ) -> None:
        self._channel = channel
        self._serializer = serializer
        self._key_fn: Callable[[T], str] = key_fn or (lambda _: "")

    @property
    def channel(self) -> Channel:
        """The underlying byte channel."""
        return self._channel

    async def send(self, value: T) -> None:
        """Serialize *value* and publish to the channel.

        The message key is computed by ``key_fn(value)`` (defaults to empty string).
        """
        payload = self._serializer.serialize(value)
        key = self._key_fn(value)
        await self._channel.send(payload, key=key)


class TypedConsumer(Generic[T]):
    """Consume typed values from a channel.

    Generic in the message type ``T``.  Uses a ``Deserializer[T]``
    to parse raw bytes into typed models.

    Usage::

        async for event in consumer.consume():
            await handle(event)
    """

    def __init__(
        self,
        channel: Channel,
        deserializer: Deserializer[T],
    ) -> None:
        self._channel = channel
        self._deserializer = deserializer

    @property
    def channel(self) -> Channel:
        """The underlying byte channel."""
        return self._channel

    async def consume(self) -> AsyncIterator[T]:
        """Yield typed messages from the channel.

        Each call creates an independent subscriber (fan-out semantics
        inherited from ``Channel.receive()``).
        """
        async for msg in self._channel.receive():
            yield self._deserializer.deserialize(msg.payload)
