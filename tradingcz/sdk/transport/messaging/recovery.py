"""RecoveryReader — one-time topic replay for startup state reconstruction.

Uses the **standard application consumer group** — no random suffixes,
no temporary groups.  Kafka's ``auto.offset.reset=earliest`` (the SDK
default) ensures the first start replays from offset 0.  After recovery,
auto-commit records the position so subsequent restarts only replay
new messages.

Design rationale
----------------
Kafka consumer group semantics give us exactly what we need:

1. **First start**: No committed offsets → ``auto.offset.reset=earliest``
   → replays every message from the beginning of the topic.
2. **Recovery consumes everything**: Messages are auto-committed as they
   are processed (``enable.auto.commit=true``).
3. **Subsequent restarts**: Committed offsets exist → resumes from the
   last committed position → only new messages are replayed.
4. **Same group for live consumption**: After recovery, calling
   ``channel.receive()`` (no suffix) on the same channel resumes
   from the last committed offset — seamless handoff.

Why NOT a separate consumer group?
    - The application OWNS its offset.  A separate group means the
      application never learns where it left off.
    - Random suffixes create many ephemeral groups — unnecessary churn.
    - The standard group with auto-commit is simpler and correct.

Usage::

    reader = RecoveryReader(events_channel, idle_timeout=2.0)
    async for msg_type, model, raw in reader.replay({
        str(EventType.DATA_REQUEST):       DataRequest,
        str(EventType.DATA_READY):         DataReady,
        str(EventType.SERVICE_LIFECYCLE):  LifecycleEvent,
    }):
        ...  # classify and reconstruct state

    # After recovery: same channel, same group, resumes from committed offset
    async for raw in events_channel.receive():
        ...  # live consumption
"""

import logging
from collections.abc import AsyncIterator

from pydantic import BaseModel

from tradingcz.sdk.transport.kafka import KafkaChannel
from tradingcz.sdk.transport.message import KafkaMessage
from tradingcz.sdk.models.headers import Header

logger = logging.getLogger(__name__)


class RecoveryReader:  # pylint: disable=too-few-public-methods
    """One-time replay of a Kafka topic for startup state recovery.

    Uses the application's standard consumer group — no temporary
    groups, no random suffixes.  Relies on Kafka's built-in offset
    management:

    - First start: ``auto.offset.reset=earliest`` → from offset 0
    - After recovery: auto-commit records position → next restart
      only replays new messages

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

        logger.debug(
            "RecoveryReader: replaying %s (idle_timeout=%.1fs)",
            self._channel.name,
            self._idle_timeout,
        )
        count = 0
        async for raw in self._channel.receive(
            idle_timeout=self._idle_timeout,
        ):
            msg_type = raw.headers.get(Header.EVENT_TYPE, "")
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
