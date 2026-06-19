"""FireAndForget — send messages on a KafkaChannel, no response expected.

Two send methods:
- ``send()``       — raw bytes + headers (any topic)
- ``send_event()`` — typed model with auto EventHeaders + KafkaKey (event topic)
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from tradingcz.sdk.transport.channel import KafkaChannel
from tradingcz.sdk.serialization.json import JsonSerializer
from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.transport.headers import EventHeaders
from tradingcz.sdk.transport.keys import KafkaKey

logger = logging.getLogger(__name__)


class FireAndForget:  # pylint: disable=too-few-public-methods
    """Send messages on a KafkaChannel.  No response expected."""

    def __init__(self, channel: KafkaChannel, service_id: str) -> None:
        self._channel = channel
        self._service_id = service_id
        self._serializer: JsonSerializer = JsonSerializer()

    # ------------------------------------------------------------------
    # Raw send — any topic, caller provides headers
    # ------------------------------------------------------------------

    async def send(self, payload: bytes, *, key: str = "", headers: dict[str, str] | None = None) -> None:
        await self._channel.send(payload, key=key, headers=headers)

    # ------------------------------------------------------------------
    # Typed send — event topic, auto-builds EventHeaders + KafkaKey
    # ------------------------------------------------------------------

    async def send_event(self, message: BaseModel, *, event_type: EventType, event_id: str, key: str = "") -> None:
        headers = EventHeaders(event_type=event_type, source_app=self._service_id, event_id=event_id).to_headers()
        if not key:
            key = KafkaKey(value=f"{event_type}:{self._service_id}:{event_id}").to_kafka()
        payload = self._serializer.serialize(message)
        await self._channel.send(payload, key=key, headers=headers)


__all__ = ["FireAndForget"]
