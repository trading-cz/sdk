"""TransportConsumer — async Kafka consumer for a single topic."""

import logging
import queue
from collections.abc import AsyncIterator, Awaitable, Callable

from confluent_kafka import TopicPartition
from confluent_kafka.aio import AIOConsumer

from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.kafka_message import KafkaMessage

logger = logging.getLogger(__name__)


class TransportConsumer:
    """Async consumer — poll, iterate, commit, error handling. One per consumer group."""

    def __init__(
        self,
        topic: str,
        settings: KafkaSettings,
        group_suffix: str,
        *,
        on_error: Callable[[int, int, str], Awaitable[None]] | None = None,
    ) -> None:
        self._topic = topic
        self._settings = settings
        self._on_error = on_error
        self._error_queue: queue.Queue[str] = queue.Queue()

        group_id = f"{self._settings.consumer_group}-{self._topic}-{group_suffix}"
        config = self._settings.consumer_config(group_id=group_id)
        self._consumer = AIOConsumer(config)
        self._subscribed = False
        self._closed = False

    # ── Core API ────────────────────────────────────────────────────────

    async def poll(self) -> list[KafkaMessage]:
        await self._ensure_subscribed()
        if self._closed:
            raise RuntimeError("TransportConsumer is closed")

        raw_msgs = await self._consumer.consume(
            num_messages=self._settings.consumer_batch_size,
            timeout=self._settings.consumer_poll_timeout_ms / 1000.0,
        )
        result: list[KafkaMessage] = []
        for msg in raw_msgs:
            if msg.error():
                await self._handle_error(msg)
                continue
            result.append(self._build_message(msg))
        return result

    async def __aiter__(self) -> AsyncIterator[KafkaMessage]:
        """Iterate messages forever — polls batches, yields each message.

        Stops only when the caller ``break``s or the task is cancelled.
        Consumer is closed automatically via ``finally`` on exit.
        """
        await self._ensure_subscribed()
        try:
            while True:
                for msg in await self.poll():
                    yield msg
        finally:
            await self._consumer.close()
            self._closed = True

    async def commit(self, msg: KafkaMessage) -> None:
        """Commit a message's offset.  Must be called during iteration."""
        await self._commit_offset(msg.topic, msg.partition, msg.offset + 1)

    async def close(self) -> None:
        if not self._closed:
            await self._consumer.close()
            self._closed = True

    def drain_errors(self) -> list[str]:
        """Pull accumulated consume errors (clears the queue)."""
        errors: list[str] = []
        while True:
            try:
                errors.append(self._error_queue.get_nowait())
            except queue.Empty:
                break
        return errors

    # ── Internal ─────────────────────────────────────────────────────────

    async def _ensure_subscribed(self) -> None:
        if not self._subscribed:
            await self._consumer.subscribe([self._topic])
            self._subscribed = True

    async def _handle_error(self, msg: object) -> None:
        """Log, invoke on_error callback, push to queue, and skip past a corrupt Kafka message."""
        partition = msg.partition() or -1
        offset = msg.offset() or -1
        error_str = str(msg.error())
        logger.error(
            "Kafka consumer error on %s [%d] offset %s: %s",
            self._topic,
            partition,
            offset,
            error_str,
        )
        self._error_queue.put(error_str)
        if self._on_error is not None:
            try:
                await self._on_error(partition, offset, error_str)
            except Exception:
                logger.exception("on_error callback raised for %s", self._topic)
        try:
            await self._commit_offset(
                msg.topic() or self._topic,
                msg.partition() or 0,
                (msg.offset() or 0) + 1,
            )
        except Exception:
            logger.exception("Failed to skip corrupt message on %s", self._topic)

    async def _commit_offset(self, topic: str, partition: int, offset: int) -> None:
        """Commit a single offset.  Shared by ``commit()`` and ``_handle_error()``."""
        await self._consumer.commit(
            offsets=[TopicPartition(topic, partition, offset)]
        )

    def _build_message(self, msg: object) -> KafkaMessage:
        """Convert a valid confluent-kafka message to a KafkaMessage DTO."""
        key = msg.key().decode() if msg.key() else ""
        headers = {
            h_key: h_val.decode() if isinstance(h_val, bytes) else str(h_val)
            for h_key, h_val in (msg.headers() or [])
        }
        return KafkaMessage(
            payload=msg.value() if msg.value() is not None else b"",
            key=key,
            headers=headers,
            offset=msg.offset() if msg.offset() is not None else -1,
            partition=msg.partition() if msg.partition() is not None else -1,
            topic=msg.topic() if msg.topic() is not None else self._topic,
        )


__all__ = ["TransportConsumer"]
