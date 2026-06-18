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
        await self._faf.send(
            signal,
            event_type=EventType.TRADING_SIGNAL,
            key=str(signal.id),
            extra_headers={"event_id": event_id},
        )


__all__ = ["SignalPublisher"]
