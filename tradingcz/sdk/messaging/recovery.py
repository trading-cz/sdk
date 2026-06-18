"""RecoveryReader — one-time topic replay for startup state reconstruction.

Uses the standard consumer group. Kafka's auto.offset.reset=earliest replays from
offset 0 on first start; auto-commit records position for subsequent restarts.

Usage::

    reader = RecoveryReader(events_channel, idle_timeout=2.0)
    async for msg_type, model, raw in reader.replay({
        str(EventType.DATA_REQUEST): DataRequest,
        str(EventType.SERVICE_LIFECYCLE): LifecycleEvent,
    }):
        ...  # reconstruct state
"""

import logging
from collections.abc import AsyncIterator

from pydantic import BaseModel

from tradingcz.sdk.transport.channel import KafkaChannel
from tradingcz.sdk.transport.message import KafkaMessage
from tradingcz.sdk.transport.headers import Header

logger = logging.getLogger(__name__)


class RecoveryReader:  # pylint: disable=too-few-public-methods
    """One-time replay of a Kafka topic for startup state recovery.

    Replays until *idle_timeout* seconds of silence, then stops.
    Uses the application's standard consumer group — no temporary groups.
    """

    def __init__(self, channel: KafkaChannel, idle_timeout: float = 2.0) -> None:
        self._channel = channel
        self._idle_timeout = idle_timeout

    async def replay(
        self,
        types: dict[str, type[BaseModel]],
    ) -> AsyncIterator[tuple[str, BaseModel, KafkaMessage]]:
        logger.info( "RecoveryReader: replaying %s (idle_timeout=%.1fs)", self._channel.name, self._idle_timeout, )
        count = 0
        async for raw in self._channel.receive(idle_timeout=self._idle_timeout):
            msg_type = raw.headers.get(Header.EVENT_TYPE, "")
            model_cls = types.get(msg_type)
            if model_cls is None:
                continue
            try:
                model = model_cls.model_validate_json(raw.payload)
            except Exception:  # pylint: disable=broad-exception-caught
                logger.info( "RecoveryReader: skip bad payload for %s on %s (offset=%d)", msg_type, self._channel.name, raw.offset, )
                continue
            count += 1
            yield msg_type, model, raw
        logger.info( "RecoveryReader: replay done — %d messages yielded on %s", count, self._channel.name, )

