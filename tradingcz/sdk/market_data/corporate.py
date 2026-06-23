"""CorporateActionsClient — dividends, splits, and capital events.

One-time (returns ``dict``):
  - ``dividends()`` — dividend history for symbols
  - ``splits()``    — stock split history for symbols
"""

from __future__ import annotations

from tradingcz.sdk.market_data._internal._transport import _DataTransport
from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.models.enums.event import AssetType, Broker, MarketDataType
from tradingcz.sdk.models.market.corporate import Dividend, StockSplit
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.kafka_topic import KafkaTopicRegistry
from tradingcz.sdk.transport.transport_producer import TransportProducer


class CorporateActionsClient:
    """Request corporate actions (dividends, splits) via RequestReply."""

    def __init__(
        self,
        *,
        rr: RequestReply | None = None,
        producer: TransportProducer | None = None,
        settings: KafkaSettings | None = None,
        topics: KafkaTopicRegistry | None = None,
        service_id: str = "",
        broker: Broker = Broker.ALPACA,
        _transport: _DataTransport | None = None,
    ) -> None:
        if _transport is not None:
            self._transport = _transport
        elif rr is not None and producer is not None and settings is not None and topics is not None:
            self._transport = _DataTransport(
                rr=rr, producer=producer, settings=settings, topics=topics,
                service_id=service_id, broker=broker,
            )
        else:
            raise ValueError("Provide _transport or (rr, producer, settings, topics, service_id)")

    async def dividends(
        self, symbols: list[str], *, days: int = 365, timeout: float = 30.0
    ) -> dict[str, list[Dividend]]:
        """Request dividend history for symbols.

        Returns ``{symbol: [Dividend sorted by ex_date]}``.
        """
        # pylint: disable=protected-access
        return await self._transport.request_historical(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.DIVIDENDS,
            model_type=Dividend,
            days=days,
            timeout=timeout,
        )

    async def splits(
        self, symbols: list[str], *, days: int = 365, timeout: float = 30.0
    ) -> dict[str, list[StockSplit]]:
        """Request stock split history for symbols.

        Returns ``{symbol: [StockSplit sorted by ex_date]}``.
        """
        # pylint: disable=protected-access
        return await self._transport.request_historical(
            symbols=symbols,
            asset=AssetType.STOCK,
            data_type=MarketDataType.SPLITS,
            model_type=StockSplit,
            days=days,
            timeout=timeout,
        )


__all__ = ["CorporateActionsClient"]
