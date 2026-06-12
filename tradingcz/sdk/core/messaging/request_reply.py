"""Generic async request-reply client over a KafkaChannel.

Publish requests with a correlation ID and await matching responses
on the same channel.  One instance handles many concurrent requests
via a single background consumer.

Generic in the request type ``Req`` and response type ``Resp``.
The caller provides serializers, deserializers, and ID extractors —
the client has no knowledge of the message schemas.

Usage::

    from tradingcz.sdk.core.messaging.request_reply import RequestReplyClient

    async with RequestReplyClient[DataRequest, DataReady | DataError](
        channel=events_channel,
        request_serializer=JsonCodec(DataRequest),
        response_deserializer=data_response_deserializer,
        request_id_of=lambda r: r.request_id,
        response_id_of=lambda r: r.request_id,
        timeout=30.0,
    ) as client:
        response = await client.request(my_data_request)
"""

import asyncio
import logging
from collections.abc import Callable

from tradingcz.sdk.core.serialization.protocol import Deserializer, Serializer
from tradingcz.sdk.core.transport.kafka import KafkaChannel

logger = logging.getLogger(__name__)


class RequestReplyClient[Req, Resp]:
    """Async request-reply over a shared KafkaChannel.

    Publish requests with ``request()`` and await correlated responses.
    A single background consumer reads all messages from *channel* and
    dispatches responses to the correct waiting caller by ID.

    One :class:`RequestReplyClient` per channel is the expected pattern.

    Generic type parameters:
        ``Req``:  The request model (e.g. ``DataRequest``).
        ``Resp``: The response model (e.g. ``DataReady | DataError``).
    """

    def __init__(
        self,
        channel: KafkaChannel,
        *,
        request_serializer: Serializer[Req],
        response_deserializer: Deserializer[Resp],
        request_id_of: Callable[[Req], str],
        response_id_of: Callable[[Resp], str],
        key_fn: Callable[[Req], str] | None = None,
        headers_fn: Callable[[Req], dict[str, str]] | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Create a new request-reply client.

        Args:
            channel: KafkaChannel for both sending requests and
                     receiving responses (typically the events topic).
            request_serializer: Converts ``Req`` to bytes.
            response_deserializer: Parses bytes into ``Resp``.
            request_id_of: Extract the correlation ID from a request.
            response_id_of: Extract the correlation ID from a response.
            key_fn: Optional Kafka message key from request.
            headers_fn: Optional Kafka headers from request.
            timeout: Per-request timeout in seconds.
        """
        self._channel = channel
        self._request_serializer = request_serializer
        self._response_deserializer = response_deserializer
        self._request_id_of = request_id_of
        self._response_id_of = response_id_of
        self._key_fn: Callable[[Req], str] = key_fn or request_id_of
        self._headers_fn = headers_fn
        self._timeout = timeout
        self._pending: dict[str, asyncio.Future[Resp]] = {}
        self._listen_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background response listener (idempotent)."""
        if self._listen_task is not None:
            return
        self._listen_task = asyncio.create_task(self._listen())

    async def close(self) -> None:
        """Cancel background listener and reject all pending futures.

        Safe to call multiple times.
        """
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                logger.debug("RequestReplyClient listener task cancelled")
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

    async def __aenter__(self) -> RequestReplyClient[Req, Resp]:
        """Async context manager entry — calls ``start()``."""
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit — calls ``close()``."""
        await self.close()

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def request(self, req: Req) -> Resp:
        """Publish *req* and wait for a correlated response.

        The request is serialized and published to the channel.
        The message key is computed by ``key_fn(req)``.
        Headers are computed by ``headers_fn(req)`` if provided.
        The background listener matches incoming responses by ID.

        Returns:
            The matched response of type ``Resp``.

        Raises:
            TimeoutError: If no response arrives within *timeout* seconds.
        """
        payload = self._request_serializer.serialize(req)
        req_id = self._request_id_of(req)
        msg_key = self._key_fn(req)
        headers = self._headers_fn(req) if self._headers_fn else None
        await self._channel.send(payload, key=msg_key, headers=headers)

        future: asyncio.Future[Resp] = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        try:
            # Use asyncio.wait (not wait_for) so that CancelledError
            # from a future cancelled by close() propagates directly
            # instead of being converted to TimeoutError by the
            # asyncio.timeout() context manager (Python 3.12+).
            done, _ = await asyncio.wait([future], timeout=self._timeout)
            if not done:
                logger.error(
                    "Request timed out after %.1fs: req_id=%s channel=%s",
                    self._timeout,
                    req_id,
                    self._channel.name,
                )
                raise TimeoutError(
                    f"Request {req_id!r} timed out after {self._timeout:.1f}s"
                )
            return future.result()
        finally:
            self._pending.pop(req_id, None)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _listen(self) -> None:
        """Background task: consume channel, dispatch responses by ID.

        Messages that fail to deserialize as ``Resp`` are silently
        skipped — this is expected on shared topics where requests
        from other services also appear.
        """
        logger.debug("RequestReplyClient listener started on %s", self._channel.name)
        try:
            async for msg in self._channel.receive():
                try:
                    resp = self._response_deserializer.deserialize(msg.payload)
                except ValueError, TypeError, LookupError:
                    # Expected: message on shared topic not meant for us
                    # (e.g. requests from other services on the same topic)
                    continue
                except Exception:
                    logger.warning(
                        "Unexpected error deserializing message on %s",
                        self._channel.name,
                        exc_info=True,
                    )
                    continue

                resp_id = self._response_id_of(resp)
                future = self._pending.get(resp_id)
                if future is not None and not future.done():
                    future.set_result(resp)
        except asyncio.CancelledError:
            logger.debug("RequestReplyClient listener cancelled")
            # Cancel all pending futures so callers don't hang forever
            for future in self._pending.values():
                if not future.done():
                    future.cancel()
        except Exception:
            logger.exception("RequestReplyClient listener error — restart recommended")
            # Reject all pending futures so callers get an error immediately
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(
                        RuntimeError("RequestReplyClient listener crashed")
                    )
