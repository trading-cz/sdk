"""SignalPublisher — publish trading signals (fire-and-forget)."""

from tradingcz.framework.helpers import FireAndForget
from tradingcz.models.enums.event import EventType
from tradingcz.models.events.execution_request_event import ExecutionRequestEvent


class SignalPublisher:
    """Publish trading signals to the event topic.

    Fire-and-forget — no response is expected.
    """

    def __init__(self, faf: FireAndForget) -> None:
        self._faf = faf

    async def publish(
        self,
        signal: ExecutionRequestEvent,
        *,
        tracking_id: str,
    ) -> None:
        """Publish a trading signal.

        Sends to the event topic with:
          - message_type = TRADING_SIGNAL
          - key = signal.id (UUID string)
          - headers: source_app, tracking_id, schema_version, sequence
        """
        await self._faf.send(
            signal,
            message_type=EventType.TRADING_SIGNAL,
            key=str(signal.id),
            extra_headers={
                "tracking_id": tracking_id,
            },
        )
