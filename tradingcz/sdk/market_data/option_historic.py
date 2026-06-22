"""OptionsHistoricDataClient — option snapshots (one-time requests).

One-time (returns ``dict``):
  - ``snapshots()`` — latest trade, quote, greeks, IV for given symbols
"""

# pylint: disable=protected-access

from __future__ import annotations

import logging

from tradingcz.sdk.market_data._internal._transport import _DataTransport
from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.models.enums.event import AssetType, Broker, MarketDataType
from tradingcz.sdk.models.market import OptionSnapshot
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.kafka_topic import KafkaTopicRegistry

logger = logging.getLogger(__name__)


class OptionsHistoricDataClient:
    """Request and consume options market data.

    Constructor args::

        OptionsHistoricDataClient(
            rr=request_reply,           # RequestReply instance (started)
            settings=kafka_settings,    # KafkaSettings
            topics=topic_registry,      # KafkaTopicRegistry
            service_id="my-service",    # unique service identifier
            broker=Broker.ALPACA,       # optional, default: ALPACA
        )

    All methods are async and return typed domain objects.
    No Kafka knowledge required beyond the constructor.
    """

    def __init__(
        self,
        *,
        rr: RequestReply,
        settings: KafkaSettings,
        topics: KafkaTopicRegistry,
        service_id: str,
        broker: Broker = Broker.ALPACA,
        _transport: _DataTransport | None = None,
    ) -> None:
        if _transport is not None:
            self._transport = _transport
        else:
            self._transport = _DataTransport(
                rr=rr, settings=settings, topics=topics,
                service_id=service_id, broker=broker,
            )

    async def snapshots(
        self, symbols: list[str], *, timeout: float = 30.0
    ) -> dict[str, list[OptionSnapshot]]:
        """Request option snapshots (trade, quote, greeks, IV).

        Returns ``{symbol: [OptionSnapshot]}``.
        """
        logger.info("OptionsHistoricDataClient: snapshots symbols=%d", len(symbols))
        return await self._transport.request_historical(
            symbols=symbols,
            asset=AssetType.OPTION,
            data_type=MarketDataType.SNAPSHOTS,
            model_type=OptionSnapshot,
            timeout=timeout,
        )


__all__ = ["OptionsHistoricDataClient"]
