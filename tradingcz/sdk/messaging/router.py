"""EventRouter — single Kafka consumer, typed handler dispatch by event_type."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, cast

from pydantic import BaseModel

from tradingcz.sdk.exceptions import ServiceNotReadyError
from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.registry import EventRegistry
from tradingcz.sdk.transport.kafka_message import KafkaMessage
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.typed.typed_consumer import TypedConsumer

logger = logging.getLogger(__name__)


@dataclass
class _Registration[T: BaseModel]:
    """Internal record for a single registered handler."""

    msg_type: EventType
    model_class: type[T]
    handler: Callable[[T, KafkaMessage], Awaitable[None]]
    filter_fn: Callable[[Any, KafkaMessage], bool] | None
    spawn_task: bool = field(default=False)


class EventRouter:
    """Single Kafka consumer.  Route messages to registered async handlers.

    Handlers run in the consume loop by default (``spawn_task=False``).
    Set ``spawn_task=True`` to run a handler in a background task — the
    spawned task is tracked and cancelled on :meth:`close`.

    When ``auto_commit=True`` (default), offsets are committed after each
    successful handler invocation, including spawned tasks.
    When ``auto_commit=False``, the handler must call :meth:`commit`
    explicitly — this is only supported for inline handlers
    (``spawn_task=False``).
    """

    def __init__(
        self,
        topic: str,
        settings: KafkaSettings,
        *,
        auto_commit: bool = True,
        on_error: Callable[[KafkaMessage], Awaitable[None]] | None = None,
        group_suffix: str,
        auto_offset_reset: str | None = None,
        poll_timeout_ms: int | None = None,
        batch_size: int | None = None,
        max_concurrency: int | None = None,
    ) -> None:
        self._topic = topic
        self._settings = settings
        self._auto_commit = auto_commit
        self._on_error = on_error
        self._group_suffix = group_suffix
        self._auto_offset_reset = auto_offset_reset
        self._poll_timeout_ms = poll_timeout_ms
        self._batch_size = batch_size
        self._handlers: dict[str, _Registration[BaseModel]] = {}
        self._consumer: TypedConsumer | None = None
        self._run_task: asyncio.Task[None] | None = None
        self._spawned_tasks: set[asyncio.Task[None]] = set()
        self._semaphore: asyncio.Semaphore | None = (
            asyncio.Semaphore(max_concurrency) if max_concurrency else None
        )

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start consuming in a background task (idempotent).

        Equivalent to calling :meth:`run` in a background task.
        Use with :meth:`close` or as an ``async with`` context manager.
        """
        if self._run_task is not None:
            return
        self._run_task = asyncio.create_task(self.run(), name=f"router-{self._topic}")

    async def close(self) -> None:
        """Cancel the background consumer task and all spawned handlers.

        Spawned handlers get *cancel_timeout* seconds to finish after
        cancellation; the consumer loop gets *cancel_timeout* seconds
        after that.  If either deadline is exceeded, a warning is logged
        and shutdown proceeds (the pod may be SIGKILL'd by Kubernetes).
        """
        cancel_timeout = 10.0
        # Cancel spawned tasks first, then the consumer loop
        for task in list(self._spawned_tasks):
            if not task.done():
                task.cancel()
        if self._spawned_tasks:
            try:
                async with asyncio.timeout(cancel_timeout):
                    await asyncio.gather(*self._spawned_tasks, return_exceptions=True)
            except TimeoutError:
                logger.warning(
                    "Timed out after %.0fs waiting for %d spawned tasks to cancel",
                    cancel_timeout,
                    len([t for t in self._spawned_tasks if not t.done()]),
                )
            self._spawned_tasks.clear()

        if self._run_task and not self._run_task.done():
            self._run_task.cancel()
            try:
                async with asyncio.timeout(cancel_timeout):
                    await self._run_task
            except asyncio.CancelledError:
                pass
            except TimeoutError:
                logger.warning(
                    "Timed out after %.0fs waiting for consumer loop to cancel",
                    cancel_timeout,
                )
        if self._consumer is not None:
            await self._consumer.close()
            self._consumer = None
        self._run_task = None

    async def __aenter__(self) -> EventRouter:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    # ── Handler registration ───────────────────────────────────────────

    async def commit(self, msg: KafkaMessage) -> None:
        """Commit a message's offset. Available during :meth:`run` or after :meth:`start`.

        Use when ``auto_commit=False`` and the handler needs explicit
        control over when the offset is committed.
        """
        if self._consumer is None:
            raise ServiceNotReadyError("commit() called outside run()")
        await self._consumer.commit(msg)

    def on[T: BaseModel](
        self,
        model_class: type[T],
        handler: Callable[[T, KafkaMessage], Awaitable[None]],
        *,
        filter_fn: Callable[[T, KafkaMessage], bool] | None = None,
        spawn_task: bool = False,
    ) -> EventRouter:
        """Register a typed handler for *model_class*.  Chainable.

        The ``EventType`` is derived from ``EventRegistry``.

        When ``spawn_task=True``, the handler runs in a background task
        tracked by the router.  ``auto_commit=False`` is **not supported**
        with spawned tasks — use inline handlers for manual commit control.
        """
        msg_type = EventRegistry.event_type_for(model_class)
        key = str(msg_type)
        if key in self._handlers:
            raise ValueError(f"Handler already registered for msg_type={key}. Existing: {self._handlers[key].model_class.__name__}, New: {model_class.__name__}")
        self._handlers[key] = _Registration(
            msg_type=msg_type,
            model_class=model_class,
            handler=handler,
            filter_fn=cast(Callable[[Any, KafkaMessage], bool] | None, filter_fn),
            spawn_task=spawn_task,
        )
        return self

    async def run(self) -> None:
        """Consume the channel until cancelled.  Dispatch each message."""
        if not self._handlers:
            logger.warning("EventRouter.run() started with no handlers registered")
            return

        types: dict[str, type[BaseModel]] = {
            str(reg.msg_type): reg.model_class
            for reg in self._handlers.values()
        }
        self._consumer = TypedConsumer(
            self._topic,
            self._settings,
            types,
            on_error=self._on_error,
            group_suffix=self._group_suffix,
            auto_commit=False,
            auto_offset_reset=self._auto_offset_reset,
            poll_timeout_ms=self._poll_timeout_ms,
            batch_size=self._batch_size,
        )

        async for msg_type, model, raw in self._consumer:
            if model is None:
                continue
            reg = self._handlers.get(msg_type)
            if reg is None:
                continue
            if reg.filter_fn is not None and not reg.filter_fn(model, raw):
                continue
            if reg.spawn_task:
                if self._semaphore:
                    await self._semaphore.acquire()
                task = asyncio.create_task(
                    self._dispatch(reg, model, raw),
                    name=f"router-{msg_type}",
                )
                self._spawned_tasks.add(task)
                task.add_done_callback(self._spawned_tasks.discard)
                if self._semaphore:
                    task.add_done_callback(lambda _: self._semaphore.release())  # type: ignore[union-attr]
            else:
                await self._dispatch(reg, model, raw)

    async def _dispatch(
        self, reg: _Registration[Any], model: BaseModel, raw: KafkaMessage
    ) -> None:
        """Invoke handler and optionally commit offset.

        On handler exception the offset is **never** committed — the
        message will be replayed on next restart (at-least-once).
        """
        try:
            await reg.handler(model, raw)
        except Exception:
            logger.exception("Handler %s failed for %s (offset=%d)", reg.handler.__name__, reg.msg_type, raw.offset)
            return  # never commit on failure — at-least-once

        if self._auto_commit and self._consumer is not None:
            await self._consumer.commit(raw)
