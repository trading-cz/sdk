"""EventRouter — single Kafka consumer, typed handler dispatch by event_type."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from types import TracebackType

from pydantic import BaseModel

from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.kafka_message import KafkaMessage
from tradingcz.sdk.typed.typed_consumer import TypedConsumer

logger = logging.getLogger(__name__)


@dataclass
class _Registration[T: BaseModel]:
    """Internal record for a single registered handler."""

    msg_type: str
    model_class: type[T]
    handler: Callable[[T, KafkaMessage], Awaitable[None]]
    filter_fn: Callable[[T, KafkaMessage], bool] | None
    spawn_task: bool = field(default=False)


class EventRouter:
    """Single Kafka consumer.  Route messages to registered async handlers.

    One instance per topic/consumer-group.  All handlers share the same
    consumer — no duplicate Kafka connections.

    Args:
        topic: Kafka topic to consume from.
        settings: Kafka connection settings.
        auto_commit: When ``True`` (default), the router commits each
            message's offset after the handler completes successfully.
            When ``False``, the handler is responsible for calling
            ``await router.commit(raw)`` explicitly.
        on_error: Optional async callback for undispatchable messages.
        group_suffix: Appended to consumer group id for isolation.

    **Offset Commit — Two Modes**

    *Mode 1 — Router auto-commit (default)*::

        router = EventRouter(topic, settings, group_suffix="signals", auto_commit=True)

        @router.on(EventType.TRADING_SIGNAL, TradingSignal, spawn_task=True)
        async def on_signal(model, raw):
            await place_order(model)
        # Router commits offset after handler returns successfully.
        # Handler raises → offset NOT committed → re-delivered.

    *Mode 2 — Manual commit (handler controls when)*::

        router = EventRouter(topic, settings, group_suffix="executor", auto_commit=False)

        @router.on(EventType.EXECUTION_REQUEST, ExecutionRequestEvent)
        async def on_request(model, raw):
            await db.save(model)          # persist first
            await router.commit(raw)      # commit offset via router
            await submit_to_broker(model) # fire-and-forget

    Commit is owned by the router (via :class:`TypedConsumer` →
    :class:`TransportConsumer`), not by :class:`KafkaMessage`.
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
    ) -> None:
        self._topic = topic
        self._settings = settings
        self._auto_commit = auto_commit
        self._on_error = on_error
        self._group_suffix = group_suffix
        self._auto_offset_reset = auto_offset_reset
        self._handlers: list[_Registration] = []
        self._consumer: TypedConsumer | None = None
        self._run_task: asyncio.Task[None] | None = None

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
        """Cancel the background consumer task and wait for it to finish."""
        if self._run_task and not self._run_task.done():
            self._run_task.cancel()
            try:
                await self._run_task
            except asyncio.CancelledError:
                pass
        self._run_task = None
        self._consumer = None

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
            raise RuntimeError("commit() called outside run()")
        await self._consumer.commit(msg)

    def on[T: BaseModel](
        self,
        msg_type: EventType,
        model_class: type[T],
        handler: Callable[[T, KafkaMessage], Awaitable[None]],
        *,
        filter_fn: Callable[[T, KafkaMessage], bool] | None = None,
        spawn_task: bool = False,
    ) -> EventRouter:
        """Register a typed handler for *msg_type*.  Chainable.

        Args:
            msg_type: The ``EventType`` this handler subscribes to.
            model_class: Pydantic model used to parse matching messages.
            handler: Async callable invoked with ``(model, raw_message)``.
            filter_fn: Optional predicate; handler is called only when it
                returns ``True``.  Receives the parsed model and raw message.
            spawn_task: When ``False`` (default) the handler is ``await``ed
                inline — next message waits until the handler completes.
                Good for fast handlers (state updates, <1 ms).
                When ``True`` an ``asyncio.Task`` is spawned per message
                so the router is not blocked.  Use for slow handlers such
                as outbound HTTP fetches.

        Returns:
            ``self`` for chaining.
        """
        self._handlers.append(
            _Registration(
                msg_type=str(msg_type),
                model_class=model_class,
                handler=handler,
                filter_fn=filter_fn,
                spawn_task=spawn_task,
            )
        )
        return self

    async def run(self) -> None:
        """Consume the channel until cancelled.  Dispatch each message.

        Internally builds a :class:`TypedConsumer` from all registered types.
        Messages whose ``message_type`` header matches no registration are
        silently skipped (TypedConsumer multi-type behaviour).

        Raises:
            asyncio.CancelledError: propagated normally on task cancellation.
        """
        if not self._handlers:
            logger.warning("EventRouter.run() started with no handlers registered")

        types: dict[str, type[BaseModel]] = {
            reg.msg_type: reg.model_class for reg in self._handlers
        }
        self._consumer = TypedConsumer(self._topic, self._settings, types, on_error=self._on_error, group_suffix=self._group_suffix, auto_commit=False, auto_offset_reset=self._auto_offset_reset)

        async for msg_type, model, raw in self._consumer:
            for reg in self._handlers:
                if reg.msg_type != msg_type:
                    continue
                if reg.filter_fn is not None and not reg.filter_fn(model, raw):  # type: ignore[arg-type]
                    continue
                if reg.spawn_task:
                    asyncio.create_task(
                        self._dispatch(reg, model, raw),
                        name=f"router-{msg_type}",
                    )
                else:
                    await self._dispatch(reg, model, raw)

    async def _dispatch(
        self,
        reg: _Registration[BaseModel],
        model: BaseModel,
        raw: KafkaMessage,
    ) -> None:
        """Invoke a handler and optionally commit the offset.

        On handler exception the offset is never committed (message
        will be re-delivered on restart — at-least-once semantics).
        When ``auto_commit`` is enabled the offset is committed after
        a successful handler invocation via the underlying
        :class:`TypedConsumer`.
        """
        try:
            await reg.handler(model, raw)  # type: ignore[arg-type]
        except Exception:
            logger.exception(
                "Handler %s failed for %s (offset=%d)",
                reg.handler.__name__,
                reg.msg_type,
                raw.offset,
            )
            return  # never commit on failure

        if self._auto_commit and self._consumer is not None:
            await self._consumer.commit(raw)
