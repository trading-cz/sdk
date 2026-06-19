"""TypedConsumer — header-based typed dispatch from a KafkaChannel (Layer 2).

Iterate typed Pydantic models from a shared multi-type Kafka topic.
Dispatches by ``event_type`` header → registered model class.

See ``typed/_README.md`` for usage examples.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable

from pydantic import BaseModel

from tradingcz.sdk.exceptions import KafkaConsumerError, MessageTypeError, SdkError
from tradingcz.sdk.serialization.json import JsonCodec
from tradingcz.sdk.transport.channel import KafkaChannel, ReceiveSession
from tradingcz.sdk.transport.headers import Header
from tradingcz.sdk.transport.message import KafkaMessage

logger = logging.getLogger(__name__)


class TypedConsumer:
    def __init__(
        self,
        channel: KafkaChannel,
        types: dict[str, type[BaseModel]],
        *,
        auto_commit: bool = True,
        on_error: Callable[[KafkaMessage], Awaitable[None]] | None = None,
        group_suffix: str = "consumer",
    ) -> None:
        self._channel = channel
        self._types = types
        self._auto_commit = auto_commit
        self._on_error = on_error
        self._group_suffix = group_suffix
        self._session: ReceiveSession | None = None

    @property
    def channel(self) -> KafkaChannel:
        return self._channel

    async def commit(self, msg: KafkaMessage) -> None:
        """Commit a message's offset. Call during iteration when ``auto_commit=False``."""
        if self._session is None:
            raise RuntimeError("commit() called outside iteration")
        await self._session.commit(msg)

    async def __aiter__(self) -> AsyncIterator[tuple[str, BaseModel, KafkaMessage]]:
        self._session = self._channel.receive(group_suffix=self._group_suffix)
        try:
            async for msg in self._session:
                try:
                    event_type, model = self._dispatch(msg)
                except SdkError:
                    await self._notify_error(msg)
                    continue
                yield event_type, model, msg
                await self._commit_if_enabled(msg)
        except KafkaConsumerError:
            logger.error(
                "Kafka consumer error on %s — terminating iteration",
                self._channel.name,
                exc_info=True,
            )

    # ── Dispatch ─────────────────────────────────────────────────────────

    def _dispatch(self, msg: KafkaMessage) -> tuple[str, BaseModel]:
        event_type = msg.headers.get(Header.EVENT_TYPE, "")
        if not event_type:
            raise MessageTypeError(
                f"Missing event_type header on {self._channel.name} (offset={msg.offset} key={msg.key!r})"
            )

        model_type = self._types.get(event_type)
        if model_type is None:
            raise MessageTypeError(
                f"Unregistered event_type {event_type!r} on {self._channel.name} (offset={msg.offset} key={msg.key!r})"
            )
        codec = JsonCodec(model_type)
        return event_type, codec.deserialize(msg.payload)

    # ── Internals ────────────────────────────────────────────────────────

    async def _commit_if_enabled(self, msg: KafkaMessage) -> None:
        if self._auto_commit and self._session is not None:
            await self._session.commit(msg)

    async def _notify_error(self, msg: KafkaMessage) -> None:
        logger.error("Caught exception while processing message on %s (offset=%d key=%r)", self._channel.name, msg.offset, msg.key, exc_info=True)
        if self._on_error is not None:
            try:
                await self._on_error(msg)
            except Exception:
                logger.warning("on_error callback raised for %s (offset=%d)", self._channel.name, msg.offset, exc_info=True)


__all__ = ["TypedConsumer"]

