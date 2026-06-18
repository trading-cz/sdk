"""KafkaChannel — Kafka-backed channel for one topic.

Uses Confluent's synchronous ``Producer`` with callback-based async wrapping
for sends (required for headers support).  ``AIOConsumer`` for receives.

One ``KafkaChannel`` per topic, one shared ``Producer`` per ``KafkaTransport``.
"""

import asyncio
import logging
from collections.abc import AsyncIterator

from confluent_kafka import Producer as ConfluentProducer
from confluent_kafka.aio import AIOConsumer

from tradingcz.sdk.transport.message import KafkaMessage
from tradingcz.sdk.transport.kafka_settings import KafkaSettings

logger = logging.getLogger(__name__)


class KafkaChannel:
    """Kafka-backed channel — one topic, fan-out receive.

    Uses a shared synchronous ``Producer`` (wrapped for async) for sends
    and creates a dedicated ``AIOConsumer`` per ``receive()`` call for
    fan-out semantics.

    All messages carry headers (``dict[str, str]``).  Headers are the
    primary mechanism for metadata (message_type, source_app, event_id,
    schema_version, sequence, etc.).
    """

    def __init__(
        self,
        topic: str,
        producer: ConfluentProducer,
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

    async def send(self, payload: bytes, *, key: str = "", headers: dict[str, str] | None = None,
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
            raise RuntimeError(f"Failed to deliver messages to {self._topic}: {remaining} message(s) still pending after flush")

    # ------------------------------------------------------------------
    # Receive
    # ------------------------------------------------------------------

    async def receive(self, *, group_suffix: str = "", idle_timeout: float = 0.0) -> AsyncIterator[KafkaMessage]:
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
                    except (UnicodeDecodeError, AttributeError):
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


__all__ = ["KafkaChannel"]
