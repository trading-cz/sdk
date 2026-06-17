"""FireAndForget — send a typed message on a KafkaChannel, no response expected.

Used internally by: SignalPublisher, HealthPublisher, ServiceApp.publish().
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from tradingcz.sdk.transport.kafka import KafkaChannel
from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.models.headers import EventHeaders

logger = logging.getLogger(__name__)


class FireAndForget:  # pylint: disable=too-few-public-methods
    """Send a typed message on a KafkaChannel.  No response expected."""

    def __init__(self, channel: KafkaChannel, service_id: str) -> None:
        self._channel = channel
        self._service_id = service_id
        self._seq = 0

    async def send(
        self,
        message: BaseModel,
        *,
        event_type: EventType,
        key: str = "",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Serialize *message* to JSON and publish with standard headers.

        Args:
            message: Pydantic model to serialize.
            event_type: :class:`EventType` enum value for the header.
            key: Kafka message key (empty = no partitioning).
            extra_headers: Additional headers merged into standard set.
        """
        self._seq += 1
        headers = EventHeaders(
            event_type=event_type,
            source_app=self._service_id,
            **(extra_headers or {}),
        ).to_kafka()
        payload = message.model_dump_json(exclude_none=True).encode()
        await self._channel.send(payload, key=key, headers=headers)
