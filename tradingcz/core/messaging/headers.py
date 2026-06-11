"""Header factories and stream producers — pre-configured publishing.

Two publishing patterns, one interface (:class:`TypedProducer`):

**Event publishing** (low throughput, explicit control)::

    from tradingcz.framework.service import ServiceApp

    await app.publish(event, message_type=EventType.DATA_READY, key=req_id)

**Stream publishing** (high throughput, fire-and-forget)::

    from tradingcz.core.messaging.headers import stream_producer

    producer = stream_producer(channel, source_app="ingestion", broker="alpaca")
    await producer.send(bar)   # auto-headers, JSON serialization, key=symbol

Both use :class:`TypedProducer` under the hood.  The difference is
**configuration**, not code — librdkafka handles batching/compression
via ``KAFKA_PRODUCER_OVERRIDES`` (e.g. ``{"linger.ms": "5"}``).

Usage::

    from tradingcz.core.messaging.headers import make_market_headers, stream_producer

    # Manual — full control over serializer, key_fn, headers_fn:
    producer = TypedProducer(
        channel=channel,
        serializer=JsonSerializer(),
        key_fn=lambda item: item.symbol,
        headers_fn=make_market_headers(source_app="ingestion", broker="alpaca"),
    )

    # Convenience — same result, less boilerplate:
    producer = stream_producer(channel, source_app="ingestion", broker="alpaca")
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from tradingcz.core.messaging.consumer import TypedProducer
from tradingcz.core.serialization import JsonSerializer
from tradingcz.core.transport.kafka import KafkaChannel
from tradingcz.models.headers import make_data_headers
from tradingcz.models.market import MarketItem, market_item_message_type


def make_market_headers(
    *,
    source_app: str,
    source: str | None = None,
    broker: str | None = None,
) -> Callable[[Any], dict[str, str]]:
    """Return a ``headers_fn`` for ``TypedProducer`` on market data channels.

    The returned callable auto-infers ``event_type`` from the item's
    class name (via :func:`market_item_message_type`) and fills in
    ``source_app``, ``source``, ``broker``, and ``symbol``.

    Args:
        source_app: Service identifier (e.g. ``"ingestion"``, ``"executor"``).
            Becomes the ``Header.SOURCE_APP`` value in every message.
        source: Optional source label.  Defaults to *source_app*.
            Becomes the ``Header.SOURCE`` value.
        broker: Broker identifier (e.g. ``"alpaca"``).  Defaults to
            the ``SDK_BROKER`` environment variable, or ``""``.

    Returns:
        A callable ``(item) → dict[str, str]`` suitable for
        ``TypedProducer(headers_fn=...)``.
    """
    _source = source or source_app
    _broker = broker or os.environ.get("SDK_BROKER", "")

    def _headers(item: Any) -> dict[str, str]:
        msg_type = market_item_message_type(item)
        return make_data_headers(
            event_type=msg_type,
            source_app=source_app,
            source=_source,
            broker=_broker,
            symbol=item.symbol,
        )

    return _headers


def stream_producer(
    channel: KafkaChannel,
    *,
    source_app: str,
    broker: str | None = None,
) -> TypedProducer[MarketItem]:
    """Create a ``TypedProducer`` pre-configured for market data streaming.

    One-liner that bundles the common stream-publishing pattern.

    **Long-lived** (stream handler keeps producer for its lifetime)::

        producer = stream_producer(channel, source_app="ingestion", broker="alpaca")
        for item in items:
            await producer.send(item)   # JSON, per-symbol key, auto-headers
        await producer.flush()          # guarantee delivery before shutdown

    **Scoped** (auto-flush on exit)::

        async with stream_producer(channel, source_app="ingestion") as producer:
            for item in items:
                await producer.send(item)
        # flush() called automatically

    Use this for high-throughput market data channels (bars, trades,
    quotes, snapshots).  For control-plane event publishing, use
    ``ServiceApp.publish()`` instead — stateless, no cleanup needed.

    Performance tuning goes through environment variables — no code
    changes needed::

        KAFKA_PRODUCER_OVERRIDES='{"linger.ms": "5", "compression.type": "snappy"}'
    """
    return TypedProducer(
        channel=channel,
        serializer=JsonSerializer(),
        key_fn=lambda item: item.symbol,  # type: ignore[union-attr]
        headers_fn=make_market_headers(source_app=source_app, broker=broker),
    )
