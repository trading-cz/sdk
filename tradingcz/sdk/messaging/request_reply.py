"""RequestReply — typed request/response over Kafka, correlated by event_id.

Uses :class:`TypedProducer` for sending and :class:`TypedConsumer` for
receiving — no manual serialization or dispatch loops.
"""

from __future__ import annotations

import asyncio
import logging
from typing import cast
from uuid import uuid4

from pydantic import BaseModel

from tradingcz.sdk.registry import EventRegistry
from tradingcz.sdk.transport.kafka_header import EventHeader, Header
from tradingcz.sdk.transport.kafka_key import KafkaKey
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.typed.typed_consumer import TypedConsumer
from tradingcz.sdk.typed.typed_producer import TypedProducer

logger = logging.getLogger(__name__)


class RequestReply:
    """Send a typed request, await a correlated typed response."""

    def __init__(
        self,
        producer: TypedProducer,
        settings: KafkaSettings,
        service_id: str,
        group_suffix: str,
        response_types: list[type[BaseModel]],
    ) -> None:
        self._typed_producer = producer
        self._settings = settings
        self._service_id = service_id
        self._response_types: dict[str, type[BaseModel]] = {
            str(EventRegistry.event_type_for(t)): t for t in response_types
        }
        self._response_event_types: set[str] = set(self._response_types.keys())
        self._pending: dict[str, asyncio.Future[BaseModel]] = {}
        self._listen_task: asyncio.Task[None] | None = None
        self._group_suffix = group_suffix
        self._correlation_id: str = ""

    # ------------------------------------------------------------------
    # Type registry
    # ------------------------------------------------------------------

    def register_type(self, model_class: type[BaseModel]) -> None:
        """Register a response type that this RequestReply can receive."""
        key = str(EventRegistry.event_type_for(model_class))
        self._response_types[key] = model_class
        self._response_event_types.add(key)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._listen_task is not None:
            return
        self._listen_task = asyncio.create_task(self._listen())

    async def close(self) -> None:
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
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    @property
    def correlation_id(self) -> str:
        return self._correlation_id

    async def request[Resp: BaseModel](  # pylint: disable=unused-argument
        self,
        req: BaseModel,
        response_type: type[Resp],  # type-checker only, not used at runtime
        *,
        timeout: float = 30.0,
    ) -> Resp:
        # Correlation is a transport concern — RequestReply generates
        # the ID, puts it in the Kafka header, and the responder echoes
        # it back.  Callers access it via .correlation_id for data-topic
        # filtering.
        self._correlation_id = str(uuid4())
        request_event_type = EventRegistry.event_type_for(req)
        _ = response_type  # used only for type-checker generic binding

        key = KafkaKey(value=f"{request_event_type.value}:{self._service_id}:{self._correlation_id}")
        headers = EventHeader(event_type=request_event_type, source_app=self._service_id, event_id=self._correlation_id)
        await self._typed_producer.send(req, key=key, headers=headers)
        await self._typed_producer.flush()

        future: asyncio.Future[Resp] = asyncio.get_running_loop().create_future()
        self._pending[self._correlation_id] = cast(asyncio.Future[BaseModel], future)

        try:
            async with asyncio.timeout(timeout):
                return await future
        except TimeoutError as e:
            raise TimeoutError(f"Request {self._correlation_id!r} timed out after {timeout:.1f}s") from e
        finally:
            self._pending.pop(self._correlation_id, None)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _listen(self) -> None:
        """Background task: TypedConsumer dispatches, resolve pending futures."""
        topic = self._typed_producer.topic
        logger.info("RequestReply listener started on %s", topic)
        consumer = TypedConsumer(
            topic=topic,
            settings=self._settings,
            types=self._response_types,
            group_suffix=self._group_suffix,
            auto_commit=True,
        )
        try:
            async for event_type, model, _raw in consumer:
                if model is None:
                    continue
                event_id: str = _raw.headers.get(Header.EVENT_ID, "")
                if event_type not in self._response_event_types:
                    logger.debug("RequestReply: skipping unregistered event_type=%s event_id=%s", event_type, event_id)
                    continue
                if not event_id:
                    logger.warning("RequestReply: message has no event_id header, skipping (event_type=%s)", event_type)
                    continue
                future = self._pending.get(event_id)
                if future is not None and not future.done():
                    future.set_result(model)
        except asyncio.CancelledError:
            logger.info("RequestReply listener cancelled")
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("RequestReply listener crashed")


__all__ = ["RequestReply"]
