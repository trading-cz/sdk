"""TransportProducer — async Kafka producer with error tracking."""

import asyncio
import logging
import queue
from collections.abc import Awaitable, Callable

from confluent_kafka import Producer as SyncProducer

from tradingcz.sdk.transport.kafka_settings import KafkaSettings

logger = logging.getLogger(__name__)


class TransportProducer:
    """Async producer — send, flush, error tracking. One per process.

    Creates the underlying :class:`confluent_kafka.Producer` from
    :class:`KafkaSettings` — no external producer needed.
    """

    def __init__(
        self,
        settings: KafkaSettings,
        *,
        on_error: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self._settings = settings
        self._producer = SyncProducer(settings.producer_config())
        self._on_error = on_error
        self._error_queue: queue.Queue[str] = queue.Queue()

    # ── Core API ────────────────────────────────────────────────────────

    async def send(
        self,
        topic: str,
        payload: bytes,
        *,
        key: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
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

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _produce)

    async def flush(self, timeout: float = 30.0) -> None:
        """Wait for all queued messages to be delivered to Kafka."""

        def _flush() -> int:
            return self._producer.flush(timeout)  # type: ignore[no-any-return]

        loop = asyncio.get_running_loop()
        remaining = await loop.run_in_executor(None, _flush)
        if remaining > 0:
            raise RuntimeError(
                f"Failed to deliver messages: {remaining} message(s) still pending after flush"
            )

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
        if err is not None:
            logger.error(
                "Delivery failed for %s [%d] offset=%s: %s",
                getattr(msg, "topic", lambda: "?")() if callable(getattr(msg, "topic", None)) else "?",
                getattr(msg, "partition", lambda: -1)() if callable(getattr(msg, "partition", None)) else -1,
                getattr(msg, "offset", lambda: -1)() if callable(getattr(msg, "offset", None)) else -1,
                err,
            )
            error_str = str(err)
            self._error_queue.put(error_str)
            if self._on_error is not None:
                asyncio.ensure_future(self._on_error(error_str))


__all__ = ["TransportProducer"]
