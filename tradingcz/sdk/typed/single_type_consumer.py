"""SingleTypeConsumer — consume a single Pydantic model type from a Kafka topic (Layer 2).

Wraps :class:`TypedConsumer` internally, adding:

* Generic ``T`` — the yield type is ``(EventType, T, KafkaMessage)``
  instead of ``(str, BaseModel, KafkaMessage)``.
* ``key_filter`` / ``header_filter`` — delegated to ``TypedConsumer``
  for pre-dispatch filtering (saves CPU on high-volume topics).

When to use: you know the topic carries (or you only care about) one
model type.  Pass ``model_type=Bar`` and iterate ``Bar`` objects.

When to use :class:`TypedConsumer` instead: the topic carries multiple
types and you need dispatch by ``event_type`` header.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Awaitable, Callable

from pydantic import BaseModel

from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.transport.kafka_message import KafkaMessage
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.typed.typed_consumer import TypedConsumer


def _model_class_to_event_type_str(model_class: type[BaseModel]) -> str:
    """Convert a Pydantic model class name to its ``EventType`` string key.

    Uses the same CamelCase → snake_case convention as
    :func:`tradingcz.sdk.models.market.market_item_message_type`::

        >>> _model_class_to_event_type_str(Bar)    # → "bar"
        >>> _model_class_to_event_type_str(Quote)  # → "quote"

    Raises ``ValueError`` if the class name does not map to a known
    ``EventType`` member.
    """
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", model_class.__name__).lower()
    return str(EventType(snake))


class SingleTypeConsumer[T: BaseModel]:
    """Consume a single Pydantic model type from a Kafka topic.

    Wraps :class:`TypedConsumer` with a single-entry ``types`` dict
    derived from *model_type*.  Yields ``(event_type, model, raw_message)``
    triples — same shape as :class:`TypedConsumer`, but with the concrete
    type ``T`` preserved.

    Two optional filter callbacks (AND logic, both run before parse):

    * ``key_filter`` — predicate on the raw Kafka key string
    * ``header_filter`` — predicate on the full header dict

    Usage::

        consumer = SingleTypeConsumer(
            topic="dev-stock-stream-bars",
            settings=kafka_settings,
            model_type=Bar,
            group_suffix="my-strategy",
            key_filter=lambda k: k in ("AAPL", "SPY"),
            header_filter=lambda h: h.get("event_id") == "abc-123",
        )
        async for event_type, model, raw in consumer:
            if model.close <= 0:      # business-level filter in your loop
                continue
            process(model)
            await consumer.commit(raw)
    """

    def __init__(
        self,
        topic: str,
        settings: KafkaSettings,
        model_type: type[T],
        *,
        group_suffix: str,
        key_filter: Callable[[str], bool] | None = None,
        header_filter: Callable[[dict[str, str]], bool] | None = None,
        auto_commit: bool = True,
        auto_offset_reset: str | None = None,
        poll_timeout_ms: int | None = None,
        batch_size: int | None = None,
        on_error: Callable[[KafkaMessage], Awaitable[None]] | None = None,
    ) -> None:
        event_type_str = _model_class_to_event_type_str(model_type)
        self._inner = TypedConsumer(
            topic=topic,
            settings=settings,
            types={event_type_str: model_type},
            group_suffix=group_suffix,
            auto_commit=False,  # wrapper controls commit
            auto_offset_reset=auto_offset_reset,
            poll_timeout_ms=poll_timeout_ms,
            batch_size=batch_size,
            on_error=on_error,
            key_filter=key_filter,
            header_filter=header_filter,
        )
        self._auto_commit = auto_commit

    async def commit(self, msg: KafkaMessage) -> None:
        """Commit a message's offset.

        Call during iteration when ``auto_commit=False``.
        """
        await self._inner.commit(msg)

    async def __aiter__(self) -> AsyncIterator[tuple[EventType, T, KafkaMessage]]:
        """Iterate typed models from the topic.

        Yields ``(event_type, model, raw_message)`` triples.  Runs
        continuously until the task is cancelled or the loop is broken.
        """
        async for et_str, model, raw in self._inner:
            event_type = EventType(et_str)
            yield event_type, model, raw  # type: ignore[arg-type,misc]
            if self._auto_commit:
                await self._inner.commit(raw)


__all__ = ["SingleTypeConsumer"]
