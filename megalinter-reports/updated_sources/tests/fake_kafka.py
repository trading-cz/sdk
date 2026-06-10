"""Fake Kafka transport for testing — uses mockafka-py for in-memory Kafka.

Provides ``FakeKafkaChannel`` and ``FakeKafkaTransport`` that mimic the real
Kafka transport layer but use ``mockafka-py`` (``FakeProducer``,
``FakeConsumer``, ``FakeAdminClientImpl``) under the hood.

Usage in tests::

    from tests.fake_kafka import FakeKafkaTransport
    from tradingcz.common.config import KafkaSettings

    settings = KafkaSettings(
        bootstrap_servers="fake:9092",
        consumer_group="test-group",
    )
    transport = FakeKafkaTransport(settings)
    channel = await transport.channel("test-topic")
    await channel.send(b"hello", key="greeting", headers={"type": "test"})

    # Consume from the same topic
    async for msg in channel.receive():
        assert msg.payload == b"hello"
        break  # receive stops after consuming available messages
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from mockafka import FakeAdminClientImpl, FakeConsumer, FakeProducer
from mockafka.admin_client import NewTopic as FakeNewTopic

from tradingcz.common.config import KafkaSettings
from tradingcz.core.transport.hash_utils import partition_for
from tradingcz.core.transport.message import KafkaMessage

logger = logging.getLogger(__name__)

# Maximum seconds to wait for new messages before stopping receive()
_RECEIVE_IDLE_TIMEOUT = 0.5


class FakeKafkaChannel:
    """In-memory Kafka channel using mockafka-py.

    Send and receive share the same in-memory message store, so messages
    produced via ``send()`` are immediately available to ``receive()``.
    """

    def __init__(
        self,
        topic: str,
        producer: FakeProducer,
        settings: KafkaSettings,
        num_partitions: int = 5,
    ) -> None:
        self._topic = topic
        self._producer = producer
        self._settings = settings
        self._num_partitions = num_partitions

    @property
    def name(self) -> str:
        """Kafka topic name."""
        return self._topic

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    async def send(
        self,
        payload: bytes,
        *,
        key: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        """Produce a message to the in-memory topic.

        Computes the partition via Murmur2 hash of the key (matching real
        Kafka behavior).  ``mockafka-py`` requires an explicit partition.
        """
        key_bytes = key.encode() if key else None
        header_list: list[tuple[str, bytes]] | None = None
        if headers:
            header_list = [(k, v.encode()) for k, v in headers.items()]

        # Compute partition from key (matching real Kafka default partitioner)
        partition = partition_for(key, self._num_partitions) if key else 0

        def _produce() -> None:
            self._producer.produce(
                self._topic,
                value=payload,
                key=key_bytes,
                partition=partition,
                headers=header_list,
            )

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _produce)

    async def flush(
        self, timeout: float = 30.0
    ) -> None:  # pylint: disable=unused-argument
        """Flush the producer (no-op for in-memory, always delivered)."""
        # In-memory produces are synchronous — nothing to flush.
        return

    # ------------------------------------------------------------------
    # Receive
    # ------------------------------------------------------------------

    async def receive(self) -> AsyncIterator[KafkaMessage]:
        """Subscribe and yield messages from the in-memory topic.

        Creates a dedicated ``FakeConsumer`` per call (fan-out semantics).
        Stops yielding after ``_RECEIVE_IDLE_TIMEOUT`` seconds of no new
        messages — this is a test convenience; real Kafka consumers run
        indefinitely.
        """
        consumer = FakeConsumer()
        consumer.subscribe([self._topic])

        try:
            while True:
                msg = consumer.poll(timeout=0.1)
                if msg is None:
                    # No message available — yield control and check again.
                    # In tests, we stop after a short idle period.
                    await asyncio.sleep(0.05)
                    # Check one more time before giving up
                    msg = consumer.poll(timeout=0.05)
                    if msg is None:
                        break
                    # else: fall through to process

                if hasattr(msg, "error") and msg.error():
                    logger.error(
                        "FakeKafka consumer error on %s: %s",
                        self._topic,
                        msg.error(),
                    )
                    continue

                # Decode key
                key = msg.key().decode() if msg.key() else ""

                # Decode headers
                raw_headers = msg.headers() or []
                headers: dict[str, str] = {}
                for h_key, h_val in raw_headers:
                    try:
                        headers[h_key] = (
                            h_val.decode() if isinstance(h_val, bytes) else str(h_val)
                        )
                    except UnicodeDecodeError, AttributeError:
                        headers[h_key] = repr(h_val)

                offset = (
                    msg.offset()
                    if hasattr(msg, "offset") and msg.offset() is not None
                    else -1
                )
                partition = (
                    msg.partition()
                    if hasattr(msg, "partition") and msg.partition() is not None
                    else -1
                )
                topic = (
                    msg.topic()
                    if hasattr(msg, "topic") and msg.topic() is not None
                    else self._topic
                )

                yield KafkaMessage(
                    payload=msg.value() if msg.value() is not None else b"",
                    key=key,
                    headers=headers,
                    offset=offset,
                    partition=partition,
                    topic=topic,
                )
        finally:
            consumer.close()

    async def close(self) -> None:
        """No-op — producer lifecycle managed by FakeKafkaTransport."""


class FakeKafkaTransport:
    """In-memory Kafka transport using mockafka-py.

    Drop-in replacement for ``KafkaTransport`` in tests.  Uses
    ``FakeProducer``, ``FakeAdminClientImpl``, and ``FakeConsumer``
    — no real Kafka connection needed.
    """

    def __init__(self, settings: KafkaSettings) -> None:
        self._settings = settings
        self._producer: FakeProducer = FakeProducer()
        self._admin = FakeAdminClientImpl()
        self._channels: dict[str, FakeKafkaChannel] = {}
        self._topics_created: set[str] = set()

    async def channel(
        self,
        name: str,
        num_partitions: int | None = None,
        replication_factor: int | None = None,  # pylint: disable=unused-argument
        retention_ms: int | None = None,  # pylint: disable=unused-argument
        cleanup_policy: str | None = None,  # pylint: disable=unused-argument
    ) -> FakeKafkaChannel:
        """Get or create a fake Kafka channel for *name*.

        Topic is auto-created on first access (in-memory, instant).
        Channels are cached by name.

        Topic creation is idempotent — if the topic already exists
        in mockafka's store, the exception is silently ignored (matching
        real Kafka's AdminClient behaviour).
        """
        if name not in self._channels:
            partitions = (
                num_partitions
                if num_partitions is not None
                else self._settings.default_num_partitions
            )
            if name not in self._topics_created:
                try:
                    self._admin.create_topics(
                        [FakeNewTopic(topic=name, num_partitions=partitions)]
                    )
                except Exception:
                    # mockafka-py raises if topic already exists;
                    # real Kafka is idempotent — ignore.
                    pass
                self._topics_created.add(name)

            self._channels[name] = FakeKafkaChannel(
                name,
                self._producer,
                self._settings,
                num_partitions=partitions,
            )
        return self._channels[name]

    async def close(self) -> None:
        """Close all channels and release transport resources."""
        for channel in self._channels.values():
            await channel.close()
        self._channels.clear()
        # Reset producer for clean state between tests
        self._producer = FakeProducer()
        self._topics_created.clear()
