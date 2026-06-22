"""Internal transport layer — re-exports from ``_internal``.

.. deprecated::
    Import from ``_internal`` directly.  This module is kept for
    backward compatibility.
"""

from tradingcz.sdk.market_data._internal._stream_handle import StreamHandle
from tradingcz.sdk.market_data._internal._transport import _DataTransport

# Backward-compat alias
BaseDataClient = _DataTransport

__all__ = ["BaseDataClient", "StreamHandle"]

