"""TransportProducer — async Kafka producer with error tracking."""

import asyncio
import logging
from collections.abc import Callable
from typing import cast

from confluent_kafka import Message, Producer as SyncProducer

from tradingcz.sdk.exceptions import TransportConnectionError, TransportError
from tradingcz.sdk.transport.kafka_settings import KafkaSettings

logger = logging.getLogger(__name__)


class TransportProducer:
    """Async producer — send, flush, error tracking. One per process.

    Args:
        settings: Kafka broker configuration.
        on_error: Optional synchronous callback invoked on delivery failure.
            Signature: ``(topic, partition, offset, error_str) -> None``.
            Runs on librdkafka's internal thread — keep it fast and
            non-blocking.  For async work, schedule on the event loop
            yourself (e.g. ``loop.call_soon_threadsafe``).
    """

    def __init__(
        self,
        settings: KafkaSettings,
        *,
        on_error: Callable[[str, int, int, str], None] | None = None,
    ) -> None:
        self._settings = settings
        self._producer = SyncProducer(settings.producer_config())
        self._on_error = on_error
        self._closed = False

    # ── Core API ────────────────────────────────────────────────────────

    async def send(
        self,
        topic: str,
        payload: bytes,
        *,
        key: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        if self._closed:
            raise TransportError("TransportProducer is closed")
        key_bytes = key.encode() if key else None
        header_list: list[tuple[str, bytes]] | None = None
        if headers:
            header_list = [(k, v.encode()) for k, v in headers.items()]

        def _produce() -> None:
            self._producer.produce(
                topic,
                value=payload,
                key=key_bytes,
                headers=header_list,
                on_delivery=self._handle_error,
            )

        await asyncio.to_thread(_produce)

    async def flush(self, timeout: float = 30.0) -> None:
        """Wait for all queued messages to be delivered to Kafka."""
        if self._closed:
            raise TransportError("TransportProducer is closed")

        def _flush() -> int:
            return cast(int, self._producer.flush(timeout))

        remaining = await asyncio.to_thread(_flush)
        if remaining > 0:
            raise TransportConnectionError(f"Failed to deliver messages: {remaining} message(s) still pending after flush")

    async def close(self) -> None:
        """Flush pending messages and mark as closed."""
        if not self._closed:
            try:
                await self.flush()
            except TransportError:
                pass  # already closed or delivery failure during shutdown
            self._closed = True

    # ── Delivery callback ────────────────────────────────────────────────

    def _handle_error(self, err: object, msg: object) -> None:
        """Delivery callback — runs on librdkafka internal thread."""
        if err is None:
            return
        kmsg = cast(Message, msg)
        try:
            topic = kmsg.topic() or "?"
            partition = kmsg.partition() or -1
            offset = kmsg.offset() or -1
        except Exception:
            logger.warning("Cannot extract metadata from delivery report", exc_info=True)
            topic = "?"
            partition = -1
            offset = -1
        error_str = str(err)
        logger.error(
            "Delivery failed for %s [%d] offset=%s: %s",
            topic, partition, offset, error_str,
        )
        if self._on_error is not None:
            try:
                self._on_error(topic, partition, offset, error_str)
            except Exception:
                logger.exception("on_error callback raised for delivery error")


__all__ = ["TransportProducer"]
