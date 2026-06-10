"""SignalPublisher — publish trading signals (fire-and-forget)."""

from tradingcz.framework.helpers import FireAndForget
from tradingcz.models.headers import MessageType
from tradingcz.models.signal import TradingSignal


class SignalPublisher:
    """Publish trading signals to the event topic.

    Fire-and-forget — no response is expected.
    """

    def __init__(self, faf: FireAndForget) -> None:
        self._faf = faf

    async def publish(
        self,
        signal: TradingSignal,
        *,
        tracking_id: str,
    ) -> None:
        """Publish a trading signal.

        Sends to the event topic with:
          - message_type = TRADING_SIGNAL
          - key = signal.symbol
          - headers: source_app, tracking_id, schema_version, sequence
        """
        await self._faf.send(
            signal,
            message_type=MessageType.TRADING_SIGNAL,
            key=signal.symbol,
            extra_headers={
                "tracking_id": tracking_id,
                "strategy_id": signal.strategy_id,
            },
        )
