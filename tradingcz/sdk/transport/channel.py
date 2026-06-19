"""KafkaChannel — one topic, one shared Producer."""

import asyncio
import logging
import queue
from collections.abc import AsyncIterator

from confluent_kafka import Producer as ConfluentProducer
from confluent_kafka import TopicPartition
from confluent_kafka.aio import AIOConsumer

from tradingcz.sdk.exceptions import KafkaConsumerError
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.message import KafkaMessage

logger = logging.getLogger(__name__)


class ReceiveSession:
    """Single-use Kafka consumer session — poll forever, commit offsets.

    Two usage modes:

    1. **Pull-based** (caller controls when to stop)::

           session = channel.receive(group_suffix="rr")
           try:
               while True:
                   msg = await session.poll()
                   if msg is None:
                       continue          # empty poll, try again
                   if done_condition(msg):
                       await session.commit(msg)
                       break
           finally:
               await session.close()

    2. **Async iterator** (convenience)::

           async for msg in channel.receive(group_suffix="consumer"):
               ...  # runs forever, break or cancel to stop

    Consumer is created eagerly (all config known at init).
    Subscription happens on first ``poll()`` or ``__aiter__`` call.
    """

    def __init__(
        self,
        topic: str,
        settings: KafkaSettings,
        group_suffix: str,
    ) -> None:
        self._topic = topic
        self._settings = settings

        group_id = f"{self._settings.consumer_group}-{self._topic}-{group_suffix}"
        config = self._settings.consumer_config(group_id=group_id)
        self._consumer = AIOConsumer(config)
        self._subscribed = False
        self._closed = False

    # ── Core API ────────────────────────────────────────────────────────

    async def poll(self) -> KafkaMessage | None:
        """Poll for the next message.  Returns ``None`` when no message
        arrives within ``consumer_poll_timeout``.  Raises
        :class:`KafkaConsumerError` on broker-level errors.

        Call in a loop for full control over stop conditions and
        idle-timeout handling.  Must call :meth:`close` when done.
        """
        await self._ensure_subscribed()
        if self._closed:
            raise RuntimeError("ReceiveSession is closed")

        msg = await self._consumer.poll(self._settings.consumer_poll_timeout)
        if msg is None:
            return None
        if msg.error():
            raise KafkaConsumerError(f"Kafka consumer error on {self._topic}: {msg.error()}")

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

    async def __aiter__(self) -> AsyncIterator[KafkaMessage]:
        await self._ensure_subscribed()
        try:
            while True:
                msg = await self.poll()
                if msg is not None:
                    yield msg
        finally:
            await self._consumer.close()
            self._closed = True

    async def commit(self, msg: KafkaMessage) -> None:
        """Commit a message's offset.  Must be called during iteration."""
        await self._consumer.commit(offsets=[TopicPartition(msg.topic, msg.partition, msg.offset + 1)])

    async def close(self) -> None:
        if not self._closed:
            await self._consumer.close()
            self._closed = True

    # ── Internal ─────────────────────────────────────────────────────────

    async def _ensure_subscribed(self) -> None:
        if not self._subscribed:
            await self._consumer.subscribe([self._topic])
            self._subscribed = True


class KafkaChannel:
    """Kafka-backed channel — one topic, shared producer, per-call consumer."""

    def __init__(
        self,
        topic: str,
        producer: ConfluentProducer,
        settings: KafkaSettings,
    ) -> None:
        self._topic = topic
        self._producer = producer
        self._settings = settings
        self._delivery_errors: queue.Queue[str] = queue.Queue()

    @property
    def name(self) -> str:
        return self._topic

    async def send(self, payload: bytes, *, key: str = "", headers: dict[str, str] | None = None) -> None:
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
                on_delivery=self._on_delivery,
            )

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _produce)


    async def flush(self, timeout: float = 30.0) -> None:
        """Wait for all queued messages to be delivered to Kafka."""

        def _flush() -> int:
            return self._producer.flush(timeout)  # type: ignore[no-any-return]

        loop = asyncio.get_running_loop()
        remaining = await loop.run_in_executor(None, _flush)
        if remaining > 0:
            raise RuntimeError(f"Failed to deliver messages to {self._topic}: {remaining} message(s) still pending after flush")

    def receive(self, *, group_suffix: str = "default") -> ReceiveSession:
        """Create a new receive session.  Use :meth:`ReceiveSession.poll` or
        ``async for`` to consume, ``commit()`` to commit offsets."""
        return ReceiveSession(
            self._topic,
            self._settings,
            group_suffix=group_suffix,
        )

    def drain_errors(self) -> list[str]:
        errors: list[str] = []
        while True:
            try:
                errors.append(self._delivery_errors.get_nowait())
            except queue.Empty:
                break
        return errors

    async def close(self) -> None:
        """No-op — producer lifecycle managed by KafkaTransport."""

    # ── Delivery callback ────────────────────────────────────────────────

    def _on_delivery(self, err: object, msg: object) -> None:
        if err is not None:
            logger.error(
                "Delivery failed for %s [%d] offset=%s: %s",
                getattr(msg, "topic", lambda: "?")() if callable(getattr(msg, "topic", None)) else "?",
                getattr(msg, "partition", lambda: -1)() if callable(getattr(msg, "partition", None)) else -1,
                getattr(msg, "offset", lambda: -1)() if callable(getattr(msg, "offset", None)) else -1,
                err,
            )
            self._delivery_errors.put(str(err))


__all__ = ["KafkaChannel", "ReceiveSession"]
