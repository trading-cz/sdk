"""Async Kafka receiver transport — request/response pattern for the event bus.

Strategy-side transport that:
  1. Publishes ``DataRequest`` messages to the shared events topic.
  2. Listens for correlated ``DataReady`` / ``DataError`` responses.
  3. Consumes raw data from ephemeral per-request topics.

Uses ``aiokafka`` for fully async Kafka interaction (no thread executors).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from tradingcz.model.events import DataError, DataReady, DataRequest, parse_event

logger = logging.getLogger(__name__)

_Response = DataReady | DataError


class AioKafkaReceiverTransport:
    """Receiver-side transport: sends DataRequests and reads responses.

    One instance per strategy run. Create → use → close.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        events_topic: str,
        *,
        consumer_group_prefix: str = "strategy",
    ) -> None:
        self._bootstrap = bootstrap_servers
        self._events_topic = events_topic
        self._group_prefix = consumer_group_prefix

        self._producer: AIOKafkaProducer | None = None
        self._consumer: AIOKafkaConsumer | None = None
        self._pending: dict[str, asyncio.Future[_Response]] = {}
        self._listen_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start producer and background response listener."""
        self._producer = AIOKafkaProducer(bootstrap_servers=self._bootstrap)
        await self._producer.start()

        group_id = f"{self._group_prefix}-receiver-{uuid.uuid4().hex[:8]}"
        self._consumer = AIOKafkaConsumer(
            self._events_topic,
            bootstrap_servers=self._bootstrap,
            group_id=group_id,
            auto_offset_reset="latest",
        )
        await self._consumer.start()
        self._listen_task = asyncio.create_task(self._response_listener())

    async def close(self) -> None:
        """Shutdown producer, background task, and consumer."""
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None
        if self._producer:
            await self._producer.stop()
            self._producer = None

    async def send_and_wait(
        self,
        request: DataRequest,
        *,
        timeout: float = 30.0,
    ) -> _Response:
        """Publish a DataRequest and block until a correlated response arrives.

        Args:
            request: The request to publish.
            timeout: Seconds to wait before raising ``TimeoutError``.

        Returns:
            ``DataReady`` or ``DataError``.

        Raises:
            TimeoutError: If no response arrives within ``timeout`` seconds.
            RuntimeError: If the transport is not started.
        """
        if self._producer is None:
            raise RuntimeError("Transport not started — call await transport.start() first")

        loop = asyncio.get_running_loop()
        future: asyncio.Future[_Response] = loop.create_future()
        self._pending[request.request_id] = future

        key = f"{request.type}:{request.event_type}:{request.broker}".encode()
        value = request.model_dump_json().encode()
        await self._producer.send_and_wait(self._events_topic, key=key, value=value)
        logger.debug(
            "DataRequest sent: type=%s symbols=%s request_id=%s",
            request.type,
            request.symbols,
            request.request_id,
        )

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(request.request_id, None)

    async def open_data_stream(self, topic: str) -> AsyncGenerator[bytes, None]:
        """Open a consumer on a per-request data topic and yield raw bytes.

        The caller controls how many messages to consume:
        - Historical: break after ``DataReady.bar_count`` messages.
        - Streaming: break when the strategy no longer needs data.

        Args:
            topic: The ephemeral data topic from ``DataReady.data_topic``.
        """
        group_id = f"{self._group_prefix}-data-{topic}"
        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=self._bootstrap,
            group_id=group_id,
            auto_offset_reset="earliest",
        )
        await consumer.start()
        try:
            async for msg in consumer:
                yield msg.value
        finally:
            await consumer.stop()

    async def _response_listener(self) -> None:
        """Background task: consume event topic, resolve pending request futures."""
        assert self._consumer is not None  # noqa: S101
        try:
            async for msg in self._consumer:
                try:
                    event = parse_event(msg.value)
                except Exception:
                    logger.debug("Skipping unparseable event message")
                    continue

                if isinstance(event, DataRequest):
                    continue

                if event.request_id in self._pending:
                    fut = self._pending[event.request_id]
                    if not fut.done():
                        fut.set_result(event)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Response listener crashed")
