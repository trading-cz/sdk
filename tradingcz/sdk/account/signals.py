"""SignalPublisher — publish trading signals (fire-and-forget)."""

from __future__ import annotations

import logging

from tradingcz.sdk.messaging.fire_and_forget import FireAndForget
from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.models.events.execution_request_event import ExecutionRequestEvent

logger = logging.getLogger(__name__)


class SignalPublisher:
    """Publish trading signals to the event topic.

    Fire-and-forget — no response is expected.
    """

    def __init__(self, faf: FireAndForget) -> None:
        self._faf = faf

    async def publish(self, signal: ExecutionRequestEvent, *, event_id: str) -> None:
        """Publish a trading signal."""
        logger.info("Signal published: strategy=%s orders=%d event_id=%s", signal.strategy_type, len(signal.orders), event_id)
        await self._faf.send(
            signal,
            event_type=EventType.TRADING_SIGNAL,
            event_id=event_id,
            key=str(signal.event_id),
        )


__all__ = ["SignalPublisher"]
