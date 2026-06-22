"""Shared mock utilities for SDK unit tests.

Provides reusable fakes for the transport/messaging layer so that individual
test files don't need to re-implement mock consumers, producers, or helpers.

Usage::

    from tests.tradingcz.sdk.mock_utils import MockConsumer, KafkaSettings, kafka_settings

    consumer = MockConsumer(
        KafkaMessage(payload=b'{"x":1}', key="", headers={"event_type": "svc.lifecycle"}, offset=0, partition=0, topic="events"),
    )
    # Use consumer as a fake async-iterable TransportConsumer/TypedConsumer
    async for msg in consumer:
        await handle(msg)
        await consumer.commit(msg)
    # Check commits: consumer.committed
"""

from __future__ import annotations

from tradingcz.sdk.transport.kafka_message import KafkaMessage
from tradingcz.sdk.transport.kafka_settings import KafkaSettings

# ── Settings factory ────────────────────────────────────────────────────────

def kafka_settings() -> KafkaSettings:
    """Create KafkaSettings with defaults suitable for unit tests (no real broker)."""
    return KafkaSettings(bootstrap_servers="localhost:9092", consumer_group="test")


# ── MockConsumer ────────────────────────────────────────────────────────────

class MockConsumer:
    """Fake async-iterable consumer yielding pre-canned :class:`KafkaMessage` objects.

    Tracks commits so tests can assert which messages were committed.

    Args:
        *messages: KafkaMessage objects to yield during iteration.

    Example::

        consumer = MockConsumer(msg1, msg2)
        async for msg in consumer:
            await process(msg)
            await consumer.commit(msg)
        assert consumer.committed == [msg1, msg2]

    Can be used as a drop-in replacement for patching
    :class:`tradingcz.sdk.transport.transport_consumer.TransportConsumer` in
    tests that exercise code iterating over a consumer.
    """

    def __init__(self, *messages: KafkaMessage) -> None:
        self._messages = list(messages)
        self._idx = 0
        self._committed: list[KafkaMessage] = []

    @property
    def committed(self) -> list[KafkaMessage]:
        """Messages that have been committed (in order)."""
        return list(self._committed)

    def was_committed(self, msg: KafkaMessage) -> bool:
        """Check whether *msg* was committed."""
        return msg in self._committed

    # ── Async iterator protocol ─────────────────────────────────────────

    def __aiter__(self) -> MockConsumer:
        self._idx = 0
        return self

    async def __anext__(self) -> KafkaMessage:
        if self._idx >= len(self._messages):
            raise StopAsyncIteration
        msg = self._messages[self._idx]
        self._idx += 1
        return msg

    # ── Consumer API (matches TransportConsumer) ─────────────────────────

    async def commit(self, msg: KafkaMessage) -> None:
        """Record a commit (matches TransportConsumer.commit signature)."""
        self._committed.append(msg)


__all__ = ["MockConsumer", "KafkaSettings", "kafka_settings"]
