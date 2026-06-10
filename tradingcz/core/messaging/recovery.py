"""RecoveryReader — one-time topic replay from offset 0.

Reads from the beginning of a Kafka topic using a temporary random
consumer group (so it does not disturb normal consumer groups), then
stops automatically after *idle_timeout* seconds of silence.

Typical use: service startup recovery — replay the events topic to
reconstruct state (what requests were made, what responses were sent)
before switching to live consumption.

Usage::

    reader = RecoveryReader(events_channel, idle_timeout=2.0)
    async for msg_type, model, raw in reader.replay({
        str(MessageType.DATA_REQUEST):       DataRequest,
        str(MessageType.DATA_READY):         DataReady,
        str(MessageType.SERVICE_LIFECYCLE):  ServiceLifecycle,
    }):
        ...  # classify and reconstruct state
"""

import logging
import os
from collections.abc import AsyncIterator

from pydantic import BaseModel

from tradingcz.models.headers import Header
from tradingcz.core.transport.kafka import KafkaChannel
from tradingcz.core.transport.message import KafkaMessage

logger = logging.getLogger(__name__)


class RecoveryReader:
    """One-time replay of a Kafka topic from offset 0.

    Uses a unique, randomly-generated consumer group suffix so each
    replay starts from the very first message on the topic (no
    committed offsets exist for the group).  The temporary group has
    no side-effects on normal consumer groups.

    The replay stops after *idle_timeout* consecutive seconds with no
    new messages — interpreted as "topic is caught up".
    """

    def __init__(self, channel: KafkaChannel, idle_timeout: float = 2.0) -> None:
        self._channel = channel
        self._idle_timeout = idle_timeout

    async def replay(
        self,
        types: dict[str, type[BaseModel]],
    ) -> AsyncIterator[tuple[str, BaseModel, KafkaMessage]]:
        """Yield ``(msg_type, model, raw_message)`` from offset 0.

        Only message types present in *types* are yielded; others are
        silently skipped.  Messages that fail Pydantic validation are
        logged at DEBUG level and skipped.

        Args:
            types: Mapping of ``message_type`` string value to Pydantic
                model class used for deserialization.

        Yields:
            ``(msg_type, parsed_model, raw_kafka_message)`` tuples.
        """
        group_suffix = f"recovery-{os.urandom(4).hex()}"
        logger.debug(
            "RecoveryReader: replaying %s (idle_timeout=%.1fs group=%s)",
            self._channel.name,
            self._idle_timeout,
            group_suffix,
        )
        count = 0
        async for raw in self._channel.receive(
            group_suffix=group_suffix,
            idle_timeout=self._idle_timeout,
        ):
            msg_type = raw.headers.get(Header.MESSAGE_TYPE, "")
            model_cls = types.get(msg_type)
            if model_cls is None:
                continue
            try:
                model = model_cls.model_validate_json(raw.payload)
            except Exception:  # pylint: disable=broad-exception-caught
                logger.debug(
                    "RecoveryReader: skip bad payload for %s on %s (offset=%d)",
                    msg_type,
                    self._channel.name,
                    raw.offset,
                )
                continue
            count += 1
            yield msg_type, model, raw
        logger.debug(
            "RecoveryReader: replay done — %d messages yielded on %s",
            count,
            self._channel.name,
        )

