"""Internal helpers for the SDK business layer.

These are NOT part of the public API.  They are used internally by
DataClient, SignalPublisher, PositionClient, etc.

- ``RequestReply``   — send a typed request, await correlated response
- ``FireAndForget``  — send a typed message, don't wait
"""

from __future__ import annotations

import asyncio
import logging
import re

from pydantic import BaseModel

from tradingcz.models.headers import Header, MessageType, build_event_key, make_headers
from tradingcz.core.transport.kafka import KafkaChannel

logger = logging.getLogger(__name__)


class FireAndForget:  # pylint: disable=too-few-public-methods
    """Send a typed message on a KafkaChannel.  No response expected.

    Used internally by: SignalPublisher.
    """

    def __init__(self, channel: KafkaChannel, service_id: str) -> None:
        self._channel = channel
        self._service_id = service_id
        self._seq = 0

    async def send(
        self,
        message: BaseModel,
        *,
        message_type: MessageType,
        key: str = "",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Serialize *message* to JSON and publish with standard headers.

        Args:
            message: Pydantic model to serialize.
            message_type: :class:`MessageType` enum value for the header.
            key: Kafka message key (empty = no partitioning).
            extra_headers: Additional headers merged into standard set.
        """
        self._seq += 1
        headers = make_headers(
            message_type=message_type,
            source_app=self._service_id,
            sequence=self._seq,
            **(extra_headers or {}),
        )
        payload = message.model_dump_json(exclude_none=True).encode()
        await self._channel.send(payload, key=key, headers=headers)


class RequestReply:
    """Send a typed request, await a correlated typed response.

    Correlation is by ``request_id`` — both request and response models
    must have a ``request_id: str`` field (convention, not Protocol).

    Uses ``make_headers()`` for consistent header construction.
    Flushes after each request to guarantee delivery before awaiting
    the response.

    Used internally by: DataClient, PositionClient, BalanceClient, OrderClient.
    """

    def __init__(
        self,
        channel: KafkaChannel,
        service_id: str,
        *,
        message_types: dict[str, type[BaseModel]] | None = None,
    ) -> None:
        self._channel = channel
        self._service_id = service_id
        self._seq = 0
        self._types: dict[str, type[BaseModel]] = dict(message_types) if message_types else {}
        self._pending: dict[str, asyncio.Future[BaseModel]] = {}
        self._listen_task: asyncio.Task[None] | None = None
        self._skipped = 0

    # ------------------------------------------------------------------
    # Type registry
    # ------------------------------------------------------------------

    def register_type(self, message_type: str | MessageType, model: type[BaseModel]) -> None:
        """Register a message_type → model mapping for response deserialization.

        Accepts both :class:`MessageType` enum values and plain strings
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

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def request[Resp: BaseModel](  # pylint: disable=unused-argument
        self,
        req: BaseModel,
        *,
        response_type: type[Resp],  # type-checker only, not used at runtime
        request_type: MessageType | None = None,
        timeout: float = 30.0,
    ) -> Resp:
        """Send *req*, await a correlated *Resp*.

        Args:
            req: The request model (must have ``request_id: str``).
            response_type: Expected response Pydantic model class.
            request_type: :class:`MessageType` enum value for the header
                (auto-inferred from the request class name if None).
            timeout: Seconds to wait before raising TimeoutError.

        Returns:
            The matched response, typed as *Resp*.

        Raises:
            TimeoutError: No correlated response within *timeout*.
            ValueError: If *req* has no ``request_id`` attribute.
        """
        request_id: str = getattr(req, "request_id", "")
        if not request_id:
            raise ValueError(f"Request model {type(req).__name__} has no request_id")

        _ = response_type  # used only for type-checker generic binding
        mt = request_type or _infer_message_type(req)
        self._seq += 1

        payload = req.model_dump_json(exclude_none=True, exclude={"timestamp"}).encode()
        headers = make_headers(
            message_type=mt,
            source_app=self._service_id,
            sequence=self._seq,
            request_id=request_id,
        )
        key = build_event_key(mt, self._service_id, request_id)
        # Send + flush — request delivery must be guaranteed before awaiting response
        await self._channel.send(payload, key=key, headers=headers)
        await self._channel.flush()

        future: asyncio.Future[Resp] = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future  # type: ignore[assignment]

        try:
            # Use asyncio.wait (not wait_for) so that CancelledError
            # from a future cancelled by close() propagates directly
            # instead of being converted to TimeoutError by the
            # asyncio.timeout() context manager (Python 3.12+).
            done, pending = await asyncio.wait([future], timeout=timeout)
            if not done:
                raise TimeoutError(
                    f"Request {request_id!r} timed out after {timeout:.1f}s"
                )
            return future.result()
        finally:
            self._pending.pop(request_id, None)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _listen(self) -> None:
        """Background task: consume channel, dispatch responses by request_id."""
        logger.debug("RequestReply listener started on %s", self._channel.name)
        try:
            async for msg in self._channel.receive():
                msg_type = msg.headers.get(Header.MESSAGE_TYPE, "")
                model_type = self._types.get(msg_type)
                if model_type is None:
                    self._skipped += 1
                    continue

                try:
                    parsed = model_type.model_validate_json(msg.payload)
                except Exception:  # pylint: disable=broad-exception-caught
                    self._skipped += 1
                    continue

                resp_id: str = getattr(parsed, Header.REQUEST_ID, "")
                if not resp_id:
                    continue

                future = self._pending.get(resp_id)
                if future is not None and not future.done():
                    future.set_result(parsed)
        except asyncio.CancelledError:
            logger.debug("RequestReply listener cancelled")
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("RequestReply listener crashed")

    @property
    def skipped_count(self) -> int:
        """Number of messages skipped (not matching any registered type)."""
        return self._skipped


def _infer_message_type(model: BaseModel) -> MessageType:
    """Infer MessageType from model class name: DataRequest → DATA_REQUEST.

    Converts CamelCase class name to snake_case and looks up the
    corresponding :class:`MessageType` enum member.

    Raises:
        ValueError: If no MessageType matches the inferred name.
            Pass an explicit ``request_type`` to avoid inference.
    """
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", type(model).__name__).lower()
    try:
        return MessageType(snake)
    except ValueError:
        raise ValueError(
            f"Cannot infer MessageType from class {type(model).__name__!r}: "
            f"'{snake}' is not a known message_type. "
            f"Pass an explicit 'request_type' parameter."
        ) from None
