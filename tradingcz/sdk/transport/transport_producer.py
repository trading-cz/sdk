"""TransportProducer — async Kafka producer with error tracking."""

import asyncio
import logging
import queue

from confluent_kafka import Producer as SyncProducer

from tradingcz.sdk.transport.kafka_settings import KafkaSettings

logger = logging.getLogger(__name__)


class TransportProducer:
    """Async producer — send, flush, error tracking. One per process."""

    def __init__(
        self,
        settings: KafkaSettings,
    ) -> None:
        self._settings = settings
        self._producer = SyncProducer(settings.producer_config())
        self._error_queue: queue.Queue[str] = queue.Queue()
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
            raise RuntimeError("TransportProducer is closed")
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
            raise RuntimeError("TransportProducer is closed")

        def _flush() -> int:
            return self._producer.flush(timeout)  # type: ignore[no-any-return]

        remaining = await asyncio.to_thread(_flush)
        if remaining > 0:
            raise RuntimeError(f"Failed to deliver messages: {remaining} message(s) still pending after flush")

    async def close(self) -> None:
        """Flush pending messages and mark as closed."""
        if not self._closed:
            try:
                await self.flush()
            except RuntimeError:
                pass  # already flushed
            self._closed = True

    def drain_errors(self) -> list[str]:
        """Pull accumulated delivery errors (clears the queue)."""
        errors: list[str] = []
        while True:
            try:
                errors.append(self._error_queue.get_nowait())
            except queue.Empty:
                break
        return errors

    # ── Delivery callback ────────────────────────────────────────────────

    def _handle_error(self, err: object, msg: object) -> None:
        """Delivery callback — runs on librdkafka internal thread.

        Thread-safe: only uses thread-safe ``queue.Queue.put()``.
        Callers retrieve errors via :meth:`drain_errors`.
        """
        if err is not None:
            logger.error(
                "Delivery failed for %s [%d] offset=%s: %s",
                getattr(msg, "topic", lambda: "?")() if callable(getattr(msg, "topic", None)) else "?",
                getattr(msg, "partition", lambda: -1)() if callable(getattr(msg, "partition", None)) else -1,
                getattr(msg, "offset", lambda: -1)() if callable(getattr(msg, "offset", None)) else -1,
                err,
            )
            self._error_queue.put(str(err))


__all__ = ["TransportProducer"]
