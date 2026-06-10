"""EventRouter — single Kafka consumer with typed handler dispatch.

One ``EventRouter`` per ``KafkaChannel``.  All handlers share the same
underlying Kafka consumer connection; there is no duplicate consumer.

Usage::

    router = EventRouter(events_channel)

    router.on(
        MessageType.DATA_REQUEST, DataRequest,
        handler=lambda req, raw: service.on_request(req),
        filter=lambda req, _: req.broker == "alpaca",
        spawn_task=True,  # historical fetch is slow
    )

    monitor = HealthMonitor(router, ttl=600)
    monitor.on_down(service.on_subscriber_down)

    await router.run()  # runs until cancelled
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pydantic import BaseModel

from tradingcz.core.messaging.consumer import TypedParser
from tradingcz.core.transport.kafka import KafkaChannel
from tradingcz.core.transport.message import KafkaMessage
from tradingcz.models.headers import MessageType

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
    """

    def __init__(self, channel: KafkaChannel) -> None:
        self._channel = channel
        self._handlers: list[_Registration] = []

    def on[T: BaseModel](
        self,
        msg_type: MessageType,
        model_class: type[T],
        handler: Callable[[T, KafkaMessage], Awaitable[None]],
        *,
        filter: (
            Callable[[T, KafkaMessage], bool] | None
        ) = None,  # noqa: A002  # pylint: disable=redefined-builtin
        spawn_task: bool = False,
    ) -> EventRouter:
        """Register a typed handler for *msg_type*.  Chainable.

        Args:
            msg_type: The ``MessageType`` this handler subscribes to.
            model_class: Pydantic model used to parse matching messages.
            handler: Async callable invoked with ``(model, raw_message)``.
            filter: Optional predicate; handler is called only when it
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
                filter_fn=filter,
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
        parser = TypedParser(self._channel, types)

        async for msg_type, model, raw in parser.parse():
            for reg in self._handlers:
                if reg.msg_type != msg_type:
                    continue
                if reg.filter_fn is not None and not reg.filter_fn(model, raw):  # type: ignore[arg-type]
                    continue
                if reg.spawn_task:
                    asyncio.create_task(
                        reg.handler(model, raw),  # type: ignore[arg-type]
                        name=f"router-{msg_type}",
                    )
                else:
                    await reg.handler(model, raw)  # type: ignore[arg-type]
