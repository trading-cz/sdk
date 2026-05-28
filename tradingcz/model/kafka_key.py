"""Deprecated — use ``tradingcz.model.headers`` instead.

``EventKey`` and ``MarketDataKey`` were previously used as JSON-serialized
Kafka message keys.  Metadata has moved to Kafka headers.  Keys are now
plain strings for partition routing.

This module is kept for backward compatibility and will be removed
in a future release.
"""

import warnings

warnings.warn(
    "tradingcz.model.kafka_key is deprecated; "
    "use tradingcz.model.headers instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export constants from headers.py for backward compatibility
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

