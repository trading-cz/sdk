"""RequestReply — typed request/response over Kafka, correlated by event_id.

Uses :class:`TypedProducer` for sending and :class:`TypedConsumer` for
receiving — no manual serialization or dispatch loops.
"""

from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel

from tradingcz.sdk.exceptions import MessageTypeError
from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.registry import EventRegistry
from tradingcz.sdk.transport.kafka_header import EventHeader, Header
from tradingcz.sdk.transport.kafka_key import KafkaKey
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.typed.typed_consumer import TypedConsumer
from tradingcz.sdk.typed.typed_producer import TypedProducer

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# RequestReply — typed request/response by event_id
# ═════════════════════════════════════════════════════════════════════════════


class RequestReply:
    """Send a typed request, await a correlated typed response."""

    def __init__(
        self,
        producer: TypedProducer,
        topic: str,
        settings: KafkaSettings,
        service_id: str,
        *,
        group_suffix: str,
        message_types: dict[EventType, type[BaseModel]] | None = None,
    ) -> None:
        self._typed_producer = producer
        self._topic = topic
        self._settings = settings
        self._service_id = service_id
        self._seq = 0
        self._types: dict[EventType, type[BaseModel]] = dict(message_types) if message_types else {}
        self._pending: dict[str, asyncio.Future[BaseModel]] = {}
        self._listen_task: asyncio.Task[None] | None = None
        self._skipped = 0
        self._group_suffix = group_suffix

    # ------------------------------------------------------------------
    # Type registry
    # ------------------------------------------------------------------

    def register_type(self, model: type[BaseModel]) -> None:
        """Register *model* for response dispatch.

        The ``EventType`` is derived from :class:`EventRegistry`.
        """
        message_type = EventRegistry.event_type_for(model)
        self._types[message_type] = model

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background listener (idempotent)."""
        if self._listen_task is not None:
            return
        self._listen_task = asyncio.create_task(self._listen())

    async def close(self) -> None:
        """Cancel listener and reject all pending futures."""
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

    async def __aenter__(self) -> RequestReply:
        """Async context manager entry — calls :meth:`start`."""
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit — calls :meth:`close`."""
        await self.close()

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def request[Resp: BaseModel](  # pylint: disable=unused-argument
        self,
        req: BaseModel,
        *,
        response_type: type[Resp],  # type-checker only, not used at runtime
        timeout: float = 30.0,
    ) -> Resp:
        # Every registered event model has event_id (UUID | str).
        # mypy can't verify this because Protocol + Union variance
        # rejects UUID as subtype of Union[UUID, str].
        event_id: str = str(req.event_id)  # type: ignore[attr-defined]
        if not event_id:
            raise MessageTypeError(f"Request model {type(req).__name__} has no event_id")

        request_type = EventRegistry.event_type_for(req)
        _ = response_type  # used only for type-checker generic binding
        self._seq += 1

        key = KafkaKey(value=f"{request_type.value}:{self._service_id}:{event_id}")
        headers = EventHeader(
            event_type=request_type,
            source_app=self._service_id,
            event_id=event_id,
        )
        # Send + flush — request delivery must be guaranteed before awaiting response
        await self._typed_producer.send(req, key=key, headers=headers)
        await self._typed_producer.flush()

        future: asyncio.Future[Resp] = asyncio.get_running_loop().create_future()
        self._pending[event_id] = future  # type: ignore[assignment]

        try:
            async with asyncio.timeout(timeout):
                return await future
        except TimeoutError:
            raise TimeoutError(f"Request {event_id!r} timed out after {timeout:.1f}s") from None
        finally:
            self._pending.pop(event_id, None)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _listen(self) -> None:
        """Background task: TypedConsumer dispatches, resolve pending futures.

        Uses :class:`TypedConsumer` for typed dispatch + auto-commit —
        no manual header parsing or serialization.
        """
        logger.debug("RequestReply listener started on %s", self._topic)
        consumer = TypedConsumer(
            topic=self._topic,
            settings=self._settings,
            types=self._types,
            group_suffix=self._group_suffix,
            auto_commit=True,
        )
        try:
            async for _msg_type, model, _raw in consumer:
                # event_id is mandatory in Kafka headers — missing → skip
                event_id: str = _raw.headers.get(Header.EVENT_ID, "")
                if not event_id:
                    logger.debug("RequestReply: message has no event_id header, skipping (type=%s)", _msg_type)
                    self._skipped += 1
                    continue
                future = self._pending.get(event_id)
                if future is not None and not future.done():
                    future.set_result(model)
        except asyncio.CancelledError:
            logger.debug("RequestReply listener cancelled")
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("RequestReply listener crashed")

    @property
    def skipped_count(self) -> int:
        """Number of messages skipped due to missing ``event_id``."""
        return self._skipped


__all__ = ["RequestReply"]
