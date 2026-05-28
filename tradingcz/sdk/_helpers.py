"""Internal helpers for the SDK business layer.

These are NOT part of the public API.  They are used internally by
DataClient, SignalPublisher, PositionClient, etc.

- ``_RequestReply``   — send a typed request, await correlated response
- ``_FireAndForget``  — send a typed message, don't wait
"""

from __future__ import annotations

import asyncio
import logging
import re

from pydantic import BaseModel

from tradingcz.model.headers import REQUEST_ID, make_headers
from tradingcz.transport.channel import KafkaChannel

logger = logging.getLogger(__name__)


class _FireAndForget:  # pylint: disable=too-few-public-methods
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
        message_type: str,
        key: str = "",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Serialize *message* to JSON and publish with standard headers.

        Args:
            message: Pydantic model to serialize.
            message_type: Value for the ``message_type`` header.
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
        payload = message.model_dump_json().encode()
        await self._channel.send(payload, key=key, headers=headers)


class _RequestReply:
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

    def register_type(self, message_type: str, model: type[BaseModel]) -> None:
        """Register a message_type → model mapping for response deserialization."""
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

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    async def request[Resp: BaseModel](  # pylint: disable=unused-argument
        self,
        req: BaseModel,
        *,
        response_type: type[Resp],  # type-checker only, not used at runtime
        request_type: str | None = None,
        timeout: float = 30.0,
    ) -> Resp:
        """Send *req*, await a correlated *Resp*.

        Args:
            req: The request model (must have ``request_id: str``).
            response_type: Expected response Pydantic model class.
            request_type: ``message_type`` header value (auto-inferred if None).
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

        payload = req.model_dump_json().encode()
        headers = make_headers(
            message_type=mt,
            source_app=self._service_id,
            sequence=self._seq,
            request_id=request_id,
        )
        # Send + flush — request delivery must be guaranteed before awaiting response
        await self._channel.send(payload, key="", headers=headers)
        await self._channel.flush()

        future: asyncio.Future[Resp] = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future  # type: ignore[arg-type]

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(request_id, None)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _listen(self) -> None:
        """Background task: consume channel, dispatch responses by request_id."""
        logger.debug("_RequestReply listener started on %s", self._channel.name)
        try:
            async for msg in self._channel.receive():
                msg_type = msg.headers.get("message_type", "")
                model_type = self._types.get(msg_type)
                if model_type is None:
                    self._skipped += 1
                    continue

                try:
                    parsed = model_type.model_validate_json(msg.payload)
                except Exception:  # pylint: disable=broad-exception-caught
                    self._skipped += 1
                    continue

                resp_id: str = getattr(parsed, REQUEST_ID, "")
                if not resp_id:
                    continue

                future = self._pending.get(resp_id)
                if future is not None and not future.done():
                    future.set_result(parsed)
        except asyncio.CancelledError:
            logger.debug("_RequestReply listener cancelled")
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("_RequestReply listener crashed")

    @property
    def skipped_count(self) -> int:
        """Number of messages skipped (not matching any registered type)."""
        return self._skipped


def _infer_message_type(model: BaseModel) -> str:
    """Infer message_type from model class name: DataRequest → 'data_request'."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", type(model).__name__).lower()
