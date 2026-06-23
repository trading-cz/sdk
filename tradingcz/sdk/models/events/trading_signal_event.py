"""TradingSignalEvent — sent by strategies to the risk manager.

Inherits all fields from :class:`ExecutionRequestEvent` and registers
under ``EventType.TRADING_SIGNAL`` in :class:`EventRegistry`.
"""

from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.models.events.execution_request_event import ExecutionRequestEvent
from tradingcz.sdk.registry import register_event


@register_event(EventType.TRADING_SIGNAL)
class TradingSignalEvent(ExecutionRequestEvent):
    """Trading signal sent by a strategy to the risk manager.

    Carries the same shape as :class:`ExecutionRequestEvent` but travels
    over Kafka with ``event_type=trading_signal`` header.
    """


__all__ = ["TradingSignalEvent"]
