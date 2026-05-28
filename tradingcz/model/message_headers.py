"""Deprecated — use ``tradingcz.model.headers`` instead.

The Pydantic header models (StandardHeaders, EventHeaders,
MarketDataHeaders, HistoricalHeaders) have been replaced by
plain constants and a ``make_headers()`` factory in
``tradingcz.model.headers``.

This module is kept for backward compatibility and will be removed
in a future release.
"""

import warnings

warnings.warn(
    "tradingcz.model.message_headers is deprecated; "
    "use tradingcz.model.headers instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from headers.py for backward compatibility
from tradingcz.model.headers import (  # noqa: F401, E402
    BROKER,
    MESSAGE_TYPE,
    REQUEST_ID,
    SCHEMA_VERSION_KEY,
    SEQUENCE,
    SOURCE,
    SOURCE_APP,
    STRATEGY_ID,
    SYMBOL,
    TRACKING_ID,
    make_headers,
)

