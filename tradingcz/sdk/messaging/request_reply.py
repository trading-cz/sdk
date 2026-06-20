"""RequestReply — typed request/response over Kafka, correlated by event_id."""

from __future__ import annotations

import asyncio
import logging
import re

from pydantic import BaseModel

from tradingcz.sdk.transport.transport_producer import TransportProducer
from tradingcz.sdk.transport.transport_consumer import TransportConsumer
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.serialization.json import JsonSerializer
from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.transport.kafka_header import EventHeader, Header
from tradingcz.sdk.transport.kafka_key import KafkaKey

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# RequestReply — typed request/response by event_id
# ═════════════════════════════════════════════════════════════════════════════


class RequestReply:
    """Send a typed request, await a correlated typed response.

    Correlation is by ``event_id`` — both request and response models
    must have a ``event_id: str`` field (convention, not Protocol).

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
        self._producer = producer
        self._topic = topic
        self._settings = settings
        self._service_id = service_id
        self._seq = 0
        self._serializer: JsonSerializer = JsonSerializer()
        self._types: dict[str, type[BaseModel]] = (dict(message_types) if message_types else {})
        self._pending: dict[str, asyncio.Future[BaseModel]] = {}
        self._listen_task: asyncio.Task[None] | None = None
        self._skipped = 0
        self._group_suffix = group_suffix

    # ------------------------------------------------------------------
    # Type registry
    # ------------------------------------------------------------------

    def register_type(self, message_type: str | EventType, model: type[BaseModel]) -> None:
        """Register a message_type → model mapping for response deserialization.

        Accepts both :class:`EventType` enum values and plain strings
        (for custom response types not in the standard enum).
        """
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

        payload = self._serializer.serialize(req)
        headers = EventHeader(
            event_type=mt,
            source_app=self._service_id,
            event_id=event_id,
        ).to_headers()
        key = KafkaKey(value=f"{mt}:{self._service_id}:{event_id}").to_kafka()
        # Send + flush — request delivery must be guaranteed before awaiting response
        await self._producer.send(self._topic, payload, key=key, headers=headers)
        await self._producer.flush()

        future: asyncio.Future[Resp] = asyncio.get_event_loop().create_future()
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
        """Background task: consume channel, dispatch responses by event_id."""
        logger.debug("RequestReply listener started on %s", self._topic)
        session = TransportConsumer(self._topic, self._settings, self._group_suffix)
        try:
            async for msg in session:
                msg_type = msg.headers.get(Header.EVENT_TYPE, "")
                model_type = self._types.get(msg_type)
                if model_type is None:
                    self._skipped += 1
                else:
                    try:
                        parsed = model_type.model_validate_json(msg.payload)
                    except Exception:  # pylint: disable=broad-exception-caught
                        self._skipped += 1
                    else:
                        resp_id: str = parsed.event_id
                        if resp_id:
                            future = self._pending.get(resp_id)
                            if future is not None and not future.done():
                                future.set_result(parsed)

                # Commit after processing (match or skip) so this offset
                # is never re-read.
                await session.commit(msg)
        except asyncio.CancelledError:
            logger.debug("RequestReply listener cancelled")
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("RequestReply listener crashed")

    @property
    def skipped_count(self) -> int:
        """Number of messages skipped (not matching any registered type)."""
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
