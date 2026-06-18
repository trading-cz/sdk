"""SignalPublisher — publish trading signals (fire-and-forget)."""

from tradingcz.sdk.messaging.fire_and_forget import FireAndForget
from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.models.events.execution_request_event import ExecutionRequestEvent


class SignalPublisher:
    """Publish trading signals to the event topic.

    Fire-and-forget — no response is expected.
    """

    def __init__(self, faf: FireAndForget) -> None:
        self._faf = faf

    async def publish(self, signal: ExecutionRequestEvent, *, event_id: str) -> None:
        """Publish a trading signal."""
        await self._faf.send_event(
            signal,
            event_type=EventType.TRADING_SIGNAL,
            event_id=event_id,
            key=str(signal.event_id),
        )


__all__ = ["SignalPublisher"]
