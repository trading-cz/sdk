"""Internal transport and streaming primitives for market data clients.

Application code never imports from this package directly.
"""

from tradingcz.sdk.market_data._internal._stream_handle import StreamHandle
from tradingcz.sdk.market_data._internal._transport import _DataTransport

__all__ = ["StreamHandle", "_DataTransport"]
