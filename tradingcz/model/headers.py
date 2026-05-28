"""Canonical Kafka header field names and factory.

Every module that builds or reads Kafka headers MUST use these constants.
No string literal header field names anywhere else in the codebase — this
module is the single source of truth.
"""

from tradingcz import SCHEMA_VERSION

# ── Standard (present on all messages) ──────────────────────────────────────
MESSAGE_TYPE = "message_type"          # e.g. "data_request", "trading_signal"
SOURCE_APP = "source_app"              # e.g. "ingestion", "my-strategy"
SCHEMA_VERSION_KEY = "schema_version"  # wire-level key for the schema version
SEQUENCE = "sequence"                  # monotonic per (source_app, topic)

# ── Event / control-plane topic ─────────────────────────────────────────────
REQUEST_ID = "request_id"              # correlation ID for request/reply
TRACKING_ID = "tracking_id"            # run identifier for signal correlation
STRATEGY_ID = "strategy_id"            # strategy that produced a signal

# ── Market-data topic ───────────────────────────────────────────────────────
SOURCE = "source"                      # origin service (e.g. "ingestion")
BROKER = "broker"                      # broker identifier (e.g. "alpaca")
SYMBOL = "symbol"                      # ticker symbol (also the Kafka key)


def make_headers(
    *,
    message_type: str,
    source_app: str = "",
    sequence: int = 0,
    schema_version: str = SCHEMA_VERSION,
    **extra: str,
) -> dict[str, str]:
    """Build a standard headers dict for any Kafka message.

    All SDK producers MUST use this factory.  Extra kwargs become
    additional header fields — e.g. ``request_id``, ``symbol``,
    ``tracking_id``, ``broker``.

    Example::

        from tradingcz.model.headers import make_headers, MESSAGE_TYPE

        h = make_headers(
            message_type="data_request",
            source_app="ingestion",
            sequence=42,
            request_id="abc123",
            symbol="AAPL",
        )
        await channel.send(payload, headers=h)

    Args:
        message_type: Header value for ``message_type`` (required).
        source_app: Origin application identifier.
        sequence: Monotonic sequence number per (source_app, topic).
        schema_version: Schema version string (default: SCHEMA_VERSION).
        **extra: Additional header fields (e.g. request_id, symbol, broker).

    Returns:
        A ``{name: value}`` dict ready for ``KafkaChannel.send(headers=...)``.
        Every value is a plain string.
    """
    headers: dict[str, str] = {
        MESSAGE_TYPE: message_type,
        SOURCE_APP: source_app,
        SCHEMA_VERSION_KEY: schema_version,
        SEQUENCE: str(sequence),
    }
    headers.update(extra)
    return headers


# ── Public API ──────────────────────────────────────────────────────────────
__all__ = [
    "MESSAGE_TYPE",
    "SOURCE_APP",
    "SCHEMA_VERSION_KEY",
    "SEQUENCE",
    "REQUEST_ID",
    "TRACKING_ID",
    "STRATEGY_ID",
    "SOURCE",
    "BROKER",
    "SYMBOL",
    "make_headers",
]
