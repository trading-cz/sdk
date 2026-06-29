"""Internal transport, streaming primitives, and provider contracts.

``StreamHandle`` and ``_DataTransport`` are internal — application code should
NOT import them directly.

``StockDataProvider`` and ``OptionDataProvider`` are the EXCEPTION: they are
the shared contracts that both SDK clients and ingestion adapters inherit from.
Prefer importing them from :mod:`tradingcz.sdk.market_data` (public re-export).
"""

from tradingcz.sdk.market_data._internal._stream_handle import StreamHandle
from tradingcz.sdk.market_data._internal._transport import _DataTransport
from tradingcz.sdk.market_data._internal.option_data_provider import OptionDataProvider
from tradingcz.sdk.market_data._internal.stock_data_provider import StockDataProvider
from tradingcz.sdk.market_data._internal.stock_stream_provider import StockStreamProvider

__all__ = [
    "StreamHandle", "_DataTransport",
    "StockDataProvider", "OptionDataProvider", "StockStreamProvider",
]
