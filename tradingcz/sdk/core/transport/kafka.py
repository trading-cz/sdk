"""Kafka-backed transport — concrete Channel and Transport.

Uses Confluent's synchronous ``Producer`` with callback-based async wrapping
for sends (required for headers support).  ``AIOConsumer`` for receives.

One ``KafkaChannel`` per topic, one shared ``Producer`` per ``KafkaTransport``.
All librdkafka parameters are configurable via ``KafkaSettings`` overrides.

Kafka is the permanent transport.  There is no abstract ``Channel``/``Transport``
layer — ``KafkaChannel`` and ``KafkaTransport`` are the direct concrete API.
"""

import asyncio
import logging
from collections.abc import AsyncIterator

from confluent_kafka import Producer as SyncProducer
from confluent_kafka.admin import AdminClient, NewTopic
from confluent_kafka.aio import AIOConsumer

from tradingcz.sdk.common.config import KafkaSettings
from tradingcz.sdk.core.transport.message import KafkaMessage

logger = logging.getLogger(__name__)


class KafkaChannel:
    """Kafka-backed channel — one topic, fan-out receive.

    Uses a shared synchronous ``Producer`` (wrapped for async) for sends
    and creates a dedicated ``AIOConsumer`` per ``receive()`` call for
    fan-out semantics.

    All messages carry headers (``dict[str, str]``).  Headers are the
    primary mechanism for metadata (message_type, source_app, request_id,
    schema_version, sequence, etc.).
    """

    def __init__(
        self,
        topic: str,
        producer: SyncProducer,
        settings: KafkaSettings,
    ) -> None:
        self._topic = topic
        self._producer = producer
        self._settings = settings

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
        """Queue a message for asynchronous delivery.  Does NOT flush.

        Messages are batched by librdkafka (``linger.ms=5`` default).
        Use ``flush()`` when you need a delivery guarantee before the
        next operation (e.g. request/reply patterns).  All queued
        messages are flushed on ``KafkaTransport.close()``.

        Args:
            payload: Message value as raw bytes (JSON in our system).
            key: Routing key (plain string, e.g. ``"AAPL"``).  Empty/None
                 means no key → round-robin across partitions.
            headers: Message headers as ``{name: value}``.  Both are UTF-8
                     encoded before sending.
        """
        key_bytes = key.encode() if key else None
        header_list: list[tuple[str, bytes]] | None = None
        if headers:
            header_list = [(k, v.encode()) for k, v in headers.items()]

        def _produce() -> None:
            self._producer.produce(
                self._topic,
                value=payload,
                key=key_bytes,
                headers=header_list,
            )

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _produce)

    async def flush(self, timeout: float = 30.0) -> None:
        """Wait for all queued messages to be delivered to Kafka.

        Call this when you need a delivery guarantee — e.g. before
        awaiting a response in a request/reply pattern.

        Args:
            timeout: Maximum seconds to wait for delivery.

        Raises:
            RuntimeError: If messages remain undelivered after timeout.
        """

        def _flush() -> int:
            return self._producer.flush(timeout)  # type: ignore[no-any-return]

        loop = asyncio.get_running_loop()
        remaining = await loop.run_in_executor(None, _flush)
        if remaining > 0:
            raise RuntimeError(
                f"Failed to deliver messages to {self._topic}: "
                f"{remaining} message(s) still pending after flush"
            )

    # ------------------------------------------------------------------
    # Receive
    # ------------------------------------------------------------------

    async def receive(
        self,
        *,
        group_suffix: str = "",
        idle_timeout: float = 0.0,
    ) -> AsyncIterator[KafkaMessage]:
        """Subscribe and yield ``KafkaMessage`` objects.

        Creates a dedicated ``AIOConsumer`` per call for fan-out semantics.
        Consumer config is fully driven by ``KafkaSettings``.

        Args:
            group_suffix: Appended to the consumer group id for isolation.
                Use a unique suffix for replay-from-beginning (fresh group
                with no committed offsets starts at ``auto.offset.reset``).
                Use a stable suffix (e.g. ``"health"``) for ongoing
                consumption that should resume from the last committed offset.
            idle_timeout: If > 0, the iterator stops after this many seconds
                of no messages.  Use for replay/drain scenarios where you
                need to read all available messages and then stop.
                Default 0 = run forever.

        Each yielded ``KafkaMessage`` carries the raw payload, decoded key,
        decoded headers, offset, partition, and topic.
        """
        base = f"{self._settings.consumer_group}-{self._topic}"
        group_id = f"{base}-{group_suffix}" if group_suffix else base
        config = self._settings.consumer_config(group_id=group_id)
        consumer = AIOConsumer(config)
        await consumer.subscribe([self._topic])

        poll_timeout = (
            min(self._settings.consumer_poll_timeout, idle_timeout)
            if idle_timeout > 0
            else self._settings.consumer_poll_timeout
        )
        idle_accum: float = 0.0

        try:
            while True:
                msg = await consumer.poll(poll_timeout)
                if msg is None:
                    if idle_timeout > 0:
                        idle_accum += poll_timeout
                        if idle_accum >= idle_timeout:
                            break
                    continue
                idle_accum = 0.0  # reset on message
                if msg.error():
                    logger.error(
                        "Kafka consumer error on %s: %s",
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

                yield KafkaMessage(
                    payload=msg.value() if msg.value() is not None else b"",
                    key=key,
                    headers=headers,
                    offset=msg.offset() if msg.offset() is not None else -1,
                    partition=msg.partition() if msg.partition() is not None else -1,
                    topic=msg.topic() if msg.topic() is not None else self._topic,
                )
        finally:
            await consumer.close()

    async def close(self) -> None:
        """No-op — producer lifecycle managed by KafkaTransport."""


class KafkaTransport:
    """Kafka-backed transport — one shared ``Producer``, cached channels.

    Topics are created on first use via Admin API if they don't already exist.
    Per-topic configuration overrides are accepted by ``channel()``.
    """

    def __init__(self, settings: KafkaSettings) -> None:
        self._settings = settings
        self._producer: SyncProducer | None = None
        self._admin = AdminClient({"bootstrap.servers": settings.bootstrap_servers})
        self._channels: dict[str, KafkaChannel] = {}
        self._topics_created: set[str] = set()

    def _get_producer(self) -> SyncProducer:
        """Lazy-init the shared synchronous Producer."""
        if self._producer is None:
            self._producer = SyncProducer(self._settings.producer_config())
        return self._producer

    async def channel(
        self,
        name: str,
        num_partitions: int | None = None,
        replication_factor: int | None = None,
        retention_ms: int | None = None,
        cleanup_policy: str | None = None,
    ) -> KafkaChannel:
        """Get or create a Kafka channel for *name*.

        Args:
            name: Kafka topic name.
            num_partitions: Override default partition count.
            replication_factor: Override default replication factor.
            retention_ms: Override default retention in milliseconds.
            cleanup_policy: Override default cleanup policy.

        All overrides are optional — when ``None``, the ``KafkaSettings``
        default is used.  Channels are cached by name, so topic config
        only applies on first call for a given name.
        """
        if name not in self._channels:
            partitions = (
                num_partitions
                if num_partitions is not None
                else self._settings.default_num_partitions
            )
            await self._ensure_topic(
                name,
                num_partitions=partitions,
                replication_factor=replication_factor,
                retention_ms=retention_ms,
                cleanup_policy=cleanup_policy,
            )
            producer = self._get_producer()
            self._channels[name] = KafkaChannel(name, producer, self._settings)
        return self._channels[name]

    async def _ensure_topic(
        self,
        name: str,
        num_partitions: int,
        replication_factor: int | None = None,
        retention_ms: int | None = None,
        cleanup_policy: str | None = None,
    ) -> None:
        """Create the topic via Admin API if it doesn't already exist."""
        if name in self._topics_created:
            return

        loop = asyncio.get_running_loop()
        metadata = await loop.run_in_executor(
            None,
            lambda: self._admin.list_topics(timeout=10),
        )
        if name in metadata.topics:
            self._topics_created.add(name)
            return

        rf = (
            replication_factor
            if replication_factor is not None
            else self._settings.default_replication_factor
        )
        ret = (
            retention_ms
            if retention_ms is not None
            else self._settings.default_retention_ms
        )
        cp = (
            cleanup_policy
            if cleanup_policy is not None
            else self._settings.default_cleanup_policy
        )

        topic_config: dict[str, str] = {"retention.ms": str(ret)}
        if cp:
            topic_config["cleanup.policy"] = cp

        new_topic = NewTopic(
            name,
            num_partitions=num_partitions,
            replication_factor=rf,
            config=topic_config,
        )
        futures = self._admin.create_topics([new_topic])
        for topic, future in futures.items():
            try:
                future.result()
                logger.info("Created topic '%s'", topic)
            except Exception as exc:
                if "TOPIC_ALREADY_EXISTS" in str(exc):
                    logger.debug(
                        "Topic '%s' already exists (race — created by another client)",
                        topic,
                    )
                else:
                    logger.exception("Failed to create topic '%s'", topic)
                    raise

        self._topics_created.add(name)

    async def close(self) -> None:
        """Close all channels and release transport resources.

        Flushes the producer to ensure all queued messages are delivered
        before shutting down.
        """
        if self._producer is not None:
            self._producer.flush(timeout=10)
            self._producer.poll(0)
        for channel in self._channels.values():
            await channel.close()
        self._channels.clear()
        self._producer = None
