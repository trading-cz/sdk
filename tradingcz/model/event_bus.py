"""EventBus — send and listen for typed events over the events channel.

Thin layer over a Channel that adds JSON serialization and
predicate-based filtering. No request/response correlation —
that logic lives in handlers.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable

from pydantic import BaseModel

from tradingcz.model.events import parse_event
from tradingcz.transport.protocol import Channel

logger = logging.getLogger(__name__)


class EventBus:
    """Send and listen for typed events on the events channel."""

    def __init__(self, channel: Channel) -> None:
        self._channel = channel

    async def send(self, event: BaseModel) -> None:
        """Serialize and publish an event to the events channel.

        Key is a JSON object with routing metadata — built here so app code never touches Kafka key formatting directly.
        """
        payload = event.model_dump_json().encode()
        key = json.dumps({
            "event_type": event.event_type,  # type: ignore[attr-defined]
            "source": getattr(event, "source_app", None) or "service",
            "request_id": getattr(event, "request_id", None),
            "ts": event.timestamp.isoformat(),  # type: ignore[attr-defined]
        })
        await self._channel.send(payload, key=key)

    async def listen(
        self,
        match: Callable[[BaseModel], bool],
    ) -> AsyncIterator[BaseModel]:
        """Yield events accepted by *match* predicate.

        Deserializes each message and applies the predicate.
        Creates an independent subscriber (fan-out).
        """
        logger.info("EventBus listen() starting on channel %s", self._channel.name)
        msg_count = 0
        async for msg in self._channel.receive():
            msg_count += 1
            if msg_count % 100 == 0 or msg_count <= 5:
                logger.debug("EventBus: received message #%d from %s", msg_count, self._channel.name)
            try:
                event = parse_event(msg.payload)
            except Exception:  # pylint: disable=broad-exception-caught
                logger.warning("Failed to parse event: %s", msg.payload[:200])
                continue
            if match(event):
                logger.debug("EventBus: event matched, yielding: %s", event.event_type)
                yield event
            else:
                logger.debug("EventBus: event not matched: %s", event.event_type)
