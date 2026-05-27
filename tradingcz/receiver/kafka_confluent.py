"""Async Kafka receiver transport using confluent-kafka (blocking API + asyncio).

Strategy-side transport that:
  1. Publishes ``DataRequest`` messages to the shared events topic.
  2. Listens for correlated ``DataReady`` / ``DataError`` responses.
  3. Consumes raw data from ephemeral per-request topics.

Uses ``confluent-kafka`` (blocking API) with asyncio executors for
async/await compatibility.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor

from confluent_kafka import Consumer, Producer

from tradingcz.model.events import DataError, DataReady, DataRequest, parse_event

logger = logging.getLogger(__name__)

_Response = DataReady | DataError


class ConfluenceKafkaReceiverTransport:
    """Receiver-side transport: sends DataRequests and reads responses.

    Uses confluent-kafka (sync) with asyncio executors for async compatibility.
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

        self._producer: Producer | None = None
        self._consumer: Consumer | None = None
        self._pending: dict[str, asyncio.Future[_Response]] = {}
        self._listen_task: asyncio.Task[None] | None = None
        self._executor: ThreadPoolExecutor | None = None

    async def start(self) -> None:
        """Start producer and background response listener."""
        loop = asyncio.get_event_loop()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="kafka-")

        # Create producer
        producer_config = {"bootstrap.servers": self._bootstrap}
        self._producer = Producer(producer_config)

        # Create consumer for events topic
        group_id = f"{self._group_prefix}-receiver-{uuid.uuid4().hex[:8]}"
        consumer_config = {
            "bootstrap.servers": self._bootstrap,
            "group.id": group_id,
            "auto.offset.reset": "latest",
            "enable.auto.commit": True,
        }
        self._consumer = Consumer(consumer_config)
        self._consumer.subscribe([self._events_topic])

        # Start background listener in executor
        self._listen_task = loop.create_task(
            loop.run_in_executor(self._executor, self._response_listener_sync)
        )

    async def close(self) -> None:
        """Shutdown producer, background task, and consumer."""
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        if self._consumer:
            self._consumer.close()
            self._consumer = None
        if self._producer:
            self._producer.flush(timeout=5.0)
            self._producer = None
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None

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

        loop = asyncio.get_event_loop()
        future: asyncio.Future[_Response] = loop.create_future()
        self._pending[request.request_id] = future

        # Send request in executor
        key = f"{request.type}:{request.event_type}:{request.broker}".encode()
        value = request.model_dump_json().encode()

        def send_sync() -> None:
            self._producer.produce(self._events_topic, key=key, value=value)
            self._producer.flush(timeout=1.0)

        await loop.run_in_executor(self._executor, send_sync)

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
        loop = asyncio.get_event_loop()
        group_id = f"{self._group_prefix}-data-{topic}"

        consumer_config = {
            "bootstrap.servers": self._bootstrap,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
        }
        consumer = Consumer(consumer_config)
        consumer.subscribe([topic])

        try:
            while True:

                def poll_sync() -> bytes | None:
                    msg = consumer.poll(timeout=1.0)
                    if msg is not None and msg.value() is not None:
                        return msg.value()
                    return None

                value = await loop.run_in_executor(self._executor, poll_sync)
                if value is not None:
                    yield value
        finally:
            consumer.close()

    def _response_listener_sync(self) -> None:
        """Blocking background task: consume event topic, resolve pending futures.

        Runs in executor thread.
        """
        assert self._consumer is not None  # noqa: S101
        try:
            while True:
                msg = self._consumer.poll(timeout=1.0)
                if msg is None:
                    continue

                if msg.value() is None:
                    continue

                try:
                    event = parse_event(msg.value())
                except Exception:  # pylint: disable=broad-exception-caught
                    logger.debug("Skipping unparseable event message")
                    continue

                if isinstance(event, DataRequest):
                    continue

                if event.request_id in self._pending:
                    fut = self._pending[event.request_id]
                    if not fut.done():
                        # Schedule callback on event loop (thread-safe)
                        asyncio.run_coroutine_threadsafe(
                            self._resolve_future(fut, event),
                            asyncio.get_event_loop(),
                        )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.exception("Response listener crashed: %s", exc)

    async def _resolve_future(self, fut: asyncio.Future[_Response], event: _Response) -> None:
        """Thread-safe helper to set future result from background thread."""
        if not fut.done():
            fut.set_result(event)
