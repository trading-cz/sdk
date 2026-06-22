"""SingleTypeConsumer — iterate one Pydantic model type from a Kafka topic."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Awaitable, Callable

from pydantic import BaseModel

from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.transport.kafka_message import KafkaMessage
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.typed.typed_consumer import TypedConsumer


def _model_class_to_event_type(model_class: type[BaseModel]) -> EventType:
    """Convert model class name to EventType (Bar → EventType.BAR)."""
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", model_class.__name__).lower()
    return EventType(snake)


class SingleTypeConsumer[T: BaseModel]:
    """Consume a single model type from a topic.  Wraps TypedConsumer.

    See ``typed/_README.md`` for usage and when to choose this over
    :class:`TypedConsumer`.
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
        event_type = _model_class_to_event_type(model_type)
        self._inner = TypedConsumer(
            topic=topic,
            settings=settings,
            types={event_type: model_type},
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
        """Commit offset.  Call during iteration when ``auto_commit=False``."""
        await self._inner.commit(msg)

    async def __aiter__(self) -> AsyncIterator[tuple[EventType, T, KafkaMessage]]:
        """Yield ``(event_type, model, raw)`` triples continuously."""
        async for event_type, model, raw in self._inner:
            yield event_type, model, raw  # type: ignore[arg-type,misc]
            if self._auto_commit:
                await self._inner.commit(raw)


__all__ = ["SingleTypeConsumer"]
