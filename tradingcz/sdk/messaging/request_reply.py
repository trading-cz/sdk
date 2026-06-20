"""RequestReply — typed request/response over Kafka, correlated by event_id.

Uses :class:`TypedProducer` for sending and :class:`TypedConsumer` for
receiving — no manual serialization or dispatch loops.
"""

from __future__ import annotations

import asyncio
import logging
import re

from pydantic import BaseModel

from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.transport.kafka_header import EventHeader
from tradingcz.sdk.transport.kafka_key import KafkaKey
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.transport_producer import TransportProducer
from tradingcz.sdk.typed.typed_consumer import TypedConsumer
from tradingcz.sdk.typed.typed_producer import TypedProducer

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# RequestReply — typed request/response by event_id
# ═════════════════════════════════════════════════════════════════════════════


class RequestReply:
    """Send a typed request, await a correlated typed response.

    Correlation is by ``event_id`` — both request and response models
    must have an ``event_id: str`` field.  Messages received on the
    response topic that lack an ``event_id`` are logged and skipped.

    Flushes after each request to guarantee delivery before awaiting
    the response.

    Used internally by: BaseDataClient, PositionClient, BalanceClient, OrderClient.
    """

    def __init__(
        self,
        producer: TransportProducer,
        topic: str,
        settings: KafkaSettings,
        service_id: str,
        *,
        group_suffix: str,
        message_types: dict[str, type[BaseModel]] | None = None,
    ) -> None:
        self._typed_producer = TypedProducer(producer, topic)
        self._topic = topic
        self._settings = settings
        self._service_id = service_id
        self._seq = 0
        self._types: dict[str, type[BaseModel]] = dict(message_types) if message_types else {}
        self._pending: dict[str, asyncio.Future[BaseModel]] = {}
        self._listen_task: asyncio.Task[None] | None = None
        self._skipped = 0
        self._group_suffix = group_suffix

    # ------------------------------------------------------------------
    # Type registry
    # ------------------------------------------------------------------

    def register_type(self, message_type: str | EventType, model: type[BaseModel]) -> None:
        self._types[str(message_type)] = model

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
        request_type: EventType | None = None,
        timeout: float = 30.0,
    ) -> Resp:
        event_id: str = str(req.event_id)
        if not event_id:
            raise ValueError(f"Request model {type(req).__name__} has no event_id")

        _ = response_type  # used only for type-checker generic binding
        mt = request_type or _infer_message_type(req)
        self._seq += 1

        key = KafkaKey(value=f"{mt}:{self._service_id}:{event_id}")
        headers = EventHeader(
            event_type=mt,
            source_app=self._service_id,
            event_id=event_id,
        )
        # Send + flush — request delivery must be guaranteed before awaiting response
        await self._typed_producer.send(req, key=key, headers=headers)
        await self._typed_producer.flush()

        future: asyncio.Future[Resp] = asyncio.get_running_loop().create_future()
        self._pending[event_id] = future  # type: ignore[assignment]

        try:
            done, _ = await asyncio.wait([future], timeout=timeout)
            if not done:
                raise TimeoutError(
                    f"Request {event_id!r} timed out after {timeout:.1f}s"
                )
            return future.result()
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
                # event_id is mandatory on the event topic — missing → skip
                event_id: str = getattr(model, 'event_id', '')
                if not event_id:
                    logger.debug(
                        "RequestReply: message has no event_id, skipping (type=%s)",
                        _msg_type,
                    )
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


def _infer_message_type(model: BaseModel) -> EventType:
    """Infer EventType from model class name: DataRequest → DATA_REQUEST.

    Converts CamelCase class name to snake_case and looks up the
    corresponding :class:`EventType` enum member.

    Raises:
        ValueError: If no EventType matches the inferred name.
            Pass an explicit ``request_type`` to avoid inference.
    """
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", type(model).__name__).lower()
    try:
        return EventType(snake)
    except ValueError:
        raise ValueError(
            f"Cannot infer EventType from class {type(model).__name__!r}: "
            f"'{snake}' is not a known EventType. "
            f"Pass an explicit 'request_type' to RequestReply.request()."
        ) from None
