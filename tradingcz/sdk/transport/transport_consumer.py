"""TransportConsumer — async Kafka consumer for a single topic."""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from confluent_kafka import TopicPartition
from confluent_kafka.aio import AIOConsumer

from tradingcz.sdk.exceptions import TransportError
from tradingcz.sdk.transport.kafka_message import KafkaMessage
from tradingcz.sdk.transport.kafka_settings import KafkaSettings

logger = logging.getLogger(__name__)


class TransportConsumer:
    """Async consumer — poll, iterate, commit, error handling. One per consumer group."""

    def __init__(
        self,
        topic: str,
        settings: KafkaSettings,
        group_suffix: str,
        *,
        auto_offset_reset: str | None = None,
        poll_timeout_ms: int | None = None,
        batch_size: int | None = None,
        auto_commit: bool = True,
        on_error: Callable[[int, int, str], Awaitable[None]] | None = None,
    ) -> None:
        self._topic = topic
        self._on_error = on_error
        self._auto_commit = auto_commit
        self._batch_size = batch_size if batch_size is not None else settings.consumer_batch_size
        self._poll_timeout_s = (poll_timeout_ms if poll_timeout_ms is not None else settings.consumer_poll_timeout_ms) / 1000.0

        self._group_id = f"{settings.consumer_group}-{topic}-{group_suffix}"
        config = settings.consumer_config(group_id=self._group_id)
        if auto_offset_reset is not None:
            config["auto.offset.reset"] = auto_offset_reset

        self._consumer = AIOConsumer(config)
        self._subscribed = False
        self._closed = False

    # ── Core API ────────────────────────────────────────────────────────

    async def poll(self) -> list[KafkaMessage]:
        if self._closed:
            raise TransportError("TransportConsumer is closed")
        await self._ensure_subscribed()

        result: list[KafkaMessage] = []
        for msg in await self._consumer.consume(num_messages=self._batch_size, timeout=self._poll_timeout_s):
            if msg.error():
                await self._handle_error(msg)
                continue
            kmsg = self._build_message(msg)
            logger.debug("TransportConsumer receive: topic=%s partition=%d offset=%d key=%r size=%dB", kmsg.topic, kmsg.partition, kmsg.offset, kmsg.key, len(kmsg.payload))
            result.append(kmsg)

        return result

    async def __aiter__(self) -> AsyncIterator[KafkaMessage]:
        """Iterate messages forever — polls batches, yields each message."""
        try:
            while True:
                for msg in await self.poll():
                    yield msg
        finally:
            await self.close()

    async def commit(self, msg: KafkaMessage) -> None:
        """Commit a message's offset.  Must be called during iteration."""
        await self._commit_offset(msg.topic, msg.partition, msg.offset + 1)

    async def close(self) -> None:
        if not self._closed:
            await self._consumer.close()
            self._closed = True
            logger.info("TransportConsumer closed: topic=%s group=%s", self._topic, self._group_id)

    # ── Internal ─────────────────────────────────────────────────────────

    async def _ensure_subscribed(self) -> None:
        if not self._subscribed:
            await self._consumer.subscribe([self._topic])
            self._subscribed = True
            logger.info("TransportConsumer subscribed: topic=%s group=%s", self._topic, self._group_id)

    async def _handle_error(self, msg: Any) -> None:
        """Log, invoke on_error callback, and conditionally skip past a corrupt Kafka message."""
        topic = msg.topic() or self._topic
        partition = msg.partition() or 0
        offset = msg.offset() or 0
        error_str = str(msg.error())
        logger.error("Kafka consumer error on %s [%d] offset %s: %s", topic, partition, offset, error_str)
        if self._on_error is not None:
            try:
                await self._on_error(partition, offset, error_str)
            except Exception:
                logger.exception("on_error callback raised for %s", self._topic)
        if self._auto_commit:
            try:
                await self._commit_offset(topic, partition, offset + 1)
            except Exception:
                logger.exception("Failed to skip corrupt message on %s", self._topic)

    async def _commit_offset(self, topic: str, partition: int, offset: int) -> None:
        """Commit a single offset.  Shared by ``commit()`` and ``_handle_error()``."""
        await self._consumer.commit(offsets=[TopicPartition(topic, partition, offset)])

    def _build_message(self, msg: Any) -> KafkaMessage:
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
