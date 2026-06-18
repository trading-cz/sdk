"""EventRouter — single Kafka consumer, typed handler dispatch by event_type."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pydantic import BaseModel

from tradingcz.sdk.messaging.pubsub import TypedParser
from tradingcz.sdk.transport.channel import KafkaChannel
from tradingcz.sdk.transport.message import KafkaMessage
from tradingcz.sdk.models.enums.event import EventType

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

    One instance per ``KafkaChannel``.  All handlers share the same
    consumer — no duplicate Kafka connections.

    Registration is done via :meth:`on` (chainable) before calling
    :meth:`run`.  Calling ``on`` after ``run`` has started has no effect
    on the running loop (not thread-safe).

    Args:
        channel: Kafka channel to consume from.
        auto_commit: When ``True`` (default), the router commits each
            message's offset after the handler completes successfully.
            When ``False``, the handler is responsible for calling
            ``await raw.commit()`` explicitly.
        on_error: Optional async callback invoked for every message
            that cannot be dispatched (missing/unknown event_type header
            or Pydantic validation failure).  Receives the raw
            ``KafkaMessage``.

    **Offset Commit — Three Modes**

    Every message from :meth:`KafkaChannel.receive` carries an
    :meth:`~KafkaMessage.commit` method.  Choose how offsets are
    committed:

    *Mode 1 — Router auto-commit (default, recommended)*::

        router = EventRouter(channel, auto_commit=True)

        @router.on(EventType.TRADING_SIGNAL, TradingSignal, spawn_task=True)
        async def on_signal(model, raw):
            await place_order(model)

        await router.run()
        # Router calls raw.commit() after on_signal completes.
        # If on_signal raises → offset NOT committed → re-delivered.

    This is "hardcoded auto-commit" — the router itself commits after
    every successful handler invocation.  Combine with
    ``enable.auto.commit=false`` in the Kafka consumer config to avoid
    librdkafka's background auto-commit (harmless but wasteful)::

        # In environment or .env:
        KAFKA_CONSUMER_OVERRIDES='{"enable.auto.commit": "false"}'

    *Mode 2 — Manual commit (handler controls when)*::

        router = EventRouter(channel, auto_commit=False)

        @router.on(EventType.EXECUTION_REQUEST, ExecutionRequestEvent)
        async def on_request(model, raw):
            await db.save(model)       # persist first
            await raw.commit()         # then commit offset
            await submit_to_broker(model)  # fire-and-forget

        await router.run()

    Use this when you need to guarantee the offset is committed ONLY
    after a side effect (e.g. DB write) succeeds — not before.

    *Mode 3 — Kafka-managed auto-commit (librdkafka)*::

        # KAFKA_CONSUMER_OVERRIDES='{"enable.auto.commit": "true"}'
        # (this is the default in KafkaSettings)

        router = EventRouter(channel, auto_commit=False)
        # librdkafka commits periodically in the background (~5 s).
        # No guarantee the handler finished before commit.

    This is the legacy behaviour — offsets drift forward regardless
    of handler outcome.  Prefer Mode 1 or 2 for trading workloads.

    **Error Notification** ::

        async def log_bad_message(raw: KafkaMessage) -> None:
            logger.error("Undispatchable message: offset=%d payload=%r",
                         raw.offset, raw.payload[:200])

        router = EventRouter(channel, on_error=log_bad_message)

    The ``on_error`` callback receives the raw ``KafkaMessage`` for
    every message that could not be dispatched — missing/unknown
    ``event_type`` header or Pydantic validation failure.  Exceptions
    raised by ``on_error`` are caught and logged; they do not crash
    the router loop.

    **Typical executor setup** (with health monitoring)::

        svc = ServiceApp(service_id="executor", env="dev", health_interval=300)
        await svc.start()

        router = EventRouter(
            svc.events_channel,
            auto_commit=False,   # handler commits after DB save
            on_error=log_bad_message,
        )
        monitor = HealthMonitor(router, ttl=600)

        router.on(EventType.TRADING_SIGNAL, TradingSignal, on_signal, spawn_task=True)
        router.on(EventType.SERVICE_REQUEST, ServiceRequestEvent, on_service_request)

        await monitor.start()
        await router.run()   # blocks until cancelled
    """

    def __init__(
        self,
        channel: KafkaChannel,
        *,
        auto_commit: bool = True,
        on_error: Callable[[KafkaMessage], Awaitable[None]] | None = None,
    ) -> None:
        self._channel = channel
        self._auto_commit = auto_commit
        self._on_error = on_error
        self._handlers: list[_Registration] = []

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

        Internally builds a :class:`TypedParser` from all registered types.
        Messages whose ``message_type`` header matches no registration are
        silently skipped (TypedParser behaviour).

        Raises:
            asyncio.CancelledError: propagated normally on task cancellation.
        """
        if not self._handlers:
            logger.warning("EventRouter.run() started with no handlers registered")

        types: dict[str, type[BaseModel]] = {
            reg.msg_type: reg.model_class for reg in self._handlers
        }
        parser = TypedParser(self._channel, types, on_error=self._on_error)

        async for msg_type, model, raw in parser.parse():
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
        a successful handler invocation.  Double-commit (handler also
        calls ``raw.commit()``) is harmless — Kafka treats it as
        idempotent.
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

        if self._auto_commit:
            try:
                await raw.commit()
            except RuntimeError:
                # Commit not available (e.g. mocked KafkaMessage in tests)
                logger.debug(
                    "Commit unavailable for %s (offset=%d) — skipping",
                    reg.msg_type,
                    raw.offset,
                )
