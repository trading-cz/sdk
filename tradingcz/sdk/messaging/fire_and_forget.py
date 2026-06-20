"""FireAndForget — send typed messages via TypedProducer, no response expected.

Builds EventHeader + KafkaKey automatically from business parameters —
caller provides event_type, event_id; the rest is handled.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.transport.kafka_header import EventHeader
from tradingcz.sdk.transport.kafka_key import KafkaKey
from tradingcz.sdk.transport.transport_producer import TransportProducer
from tradingcz.sdk.typed.typed_producer import TypedProducer

logger = logging.getLogger(__name__)


class FireAndForget:  # pylint: disable=too-few-public-methods
    """Send typed messages via TypedProducer.  No response expected."""

    def __init__(self, producer: TransportProducer, topic: str, service_id: str) -> None:
        self._typed = TypedProducer(producer, topic)
        self._service_id = service_id

    async def send(self, message: BaseModel, *, event_type: EventType, event_id: str, key: str = "") -> None:
        kafka_key = KafkaKey(value=key or f"{event_type}:{self._service_id}:{event_id}")
        headers = EventHeader(event_type=event_type, source_app=self._service_id, event_id=event_id)
        await self._typed.send(message, key=kafka_key, headers=headers)
        await self._typed.flush()


__all__ = ["FireAndForget"]
