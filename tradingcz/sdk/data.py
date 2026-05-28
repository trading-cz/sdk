"""DataClient — request and consume market data (historical + streaming).

Handles the full lifecycle:
  1. Send DataRequest via _RequestReply
  2. Await DataReady (contains data_topic for stream/historical topics)
  3. Manage ephemeral channels or streaming subscriptions
  4. Filter, order, parse, and yield typed results
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from tradingcz.model.events import DataError, DataReady, DataRequest
from tradingcz.model.headers import REQUEST_ID, SEQUENCE, SOURCE, SOURCE_APP
from tradingcz.model.ingestion import Bar, StreamQuote, Trade
from tradingcz.sdk._helpers import _RequestReply
from tradingcz.transport._dedup import DedupFilter
from tradingcz.transport.channel import KafkaTransport
from tradingcz.transport.topics import TopicRegistry

logger = logging.getLogger(__name__)


class DataClient:
    """Request and consume market data.

    All methods are async and return typed domain objects.
    No Kafka knowledge required.

    Deduplication is enabled by default: messages with the same
    ``(source, sequence)`` header pair are skipped.  This handles
    at-least-once Kafka delivery after consumer restarts.
    """

    def __init__(
        self,
        rr: _RequestReply,
        transport: KafkaTransport,
        topics: TopicRegistry,
        service_id: str,
        broker: str = "alpaca",
        *,
        dedup_max_size: int = 100_000,
    ) -> None:
        self._rr = rr
        self._transport = transport
        self._topics = topics
        self._service_id = service_id
        self._broker = broker
        self._dedup = DedupFilter(max_size=dedup_max_size)
        # Register response types
        rr.register_type("data_ready", DataReady)
        rr.register_type("data_error", DataError)

    @property
    def dedup_skipped(self) -> int:
        """Number of duplicate messages skipped by the dedup filter."""
        return self._dedup.skipped_count

    # ------------------------------------------------------------------
    # Historical
    # ------------------------------------------------------------------

    async def request_historical(
        self,
        symbols: list[str],
        *,
        days: int = 14,
        timeframe: str = "1d",
        timeout: float = 30.0,
    ) -> dict[str, list[Bar]]:
        """Request historical daily bars.

        Returns ``{symbol: [Bar sorted by timestamp]}``.
        """
        end = datetime.now(UTC)
        start = end - timedelta(days=days)

        req = DataRequest(
            type="historic",
            asset="stock",
            broker=self._broker,
            symbols=symbols,
            timeframe=timeframe,
            start_time=start,
            end_time=end,
            source_app=self._service_id,
        )

        resp = await self._rr.request(
            req,
            response_type=DataReady,
            request_type="data_request",
            timeout=timeout,
        )

        if isinstance(resp, DataError):
            raise RuntimeError(f"DataError from ingestion: {resp.error}")

        if resp.type != "historic":
            raise RuntimeError(f"Expected historic DataReady, got type={resp.type}")

        logger.info(
            "DataReady(historic): topic=%s bar_count=%s",
            resp.data_topic,
            resp.bar_count,
        )

        # Open ephemeral channel and consume bars
        channel = await self._transport.channel(resp.data_topic)
        bars_by_symbol: dict[str, list[Bar]] = {}
        count = 0
        expected = resp.bar_count or 0

        try:
            async for msg in channel.receive():
                # Filter by request_id in headers
                if msg.headers.get(REQUEST_ID) != req.request_id:
                    continue
                # Dedup by (source, sequence)
                if self._dedup.is_duplicate(
                    msg.headers.get(SOURCE, msg.headers.get(SOURCE_APP, "")),
                    msg.headers.get(SEQUENCE, "0"),
                ):
                    continue
                try:
                    bar = Bar.model_validate_json(msg.payload)
                except Exception:
                    logger.debug("Skipping unparseable bar", exc_info=True)
                    continue
                bars_by_symbol.setdefault(bar.symbol, []).append(bar)
                count += 1
                if expected and count >= expected:
                    break
        finally:
            await channel.close()

        # Sort by timestamp within each symbol
        for symbol_bars in bars_by_symbol.values():
            symbol_bars.sort(key=lambda b: b.timestamp)

        return bars_by_symbol

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    async def stream_quotes(
        self,
        symbols: list[str],
        *,
        timeout: float = 30.0,
    ) -> AsyncIterator[StreamQuote]:
        """Stream live quotes. Yields ``StreamQuote`` objects."""
        async for quote in self._stream(
            symbols=symbols,
            stream_type="quotes",
            model_type=StreamQuote,
            timeout=timeout,
        ):
            yield quote  # type: ignore[misc]

    async def stream_trades(
        self,
        symbols: list[str],
        *,
        timeout: float = 30.0,
    ) -> AsyncIterator[Trade]:
        """Stream live trades. Yields ``Trade`` objects."""
        async for trade in self._stream(
            symbols=symbols,
            stream_type="trades",
            model_type=Trade,
            timeout=timeout,
        ):
            yield trade  # type: ignore[misc]

    async def _stream[T](
        self,
        symbols: list[str],
        stream_type: str,
        model_type: type[T],
        timeout: float,
    ) -> AsyncIterator[T]:
        """Internal: send DataRequest, open stream channel, yield typed items."""
        req = DataRequest(
            type="stream",
            asset="stock",
            broker=self._broker,
            symbols=symbols,
            stream_type=stream_type,
            source_app=self._service_id,
        )

        resp = await self._rr.request(
            req,
            response_type=DataReady,
            request_type="data_request",
            timeout=timeout,
        )

        if isinstance(resp, DataError):
            raise RuntimeError(f"DataError from ingestion (stream): {resp.error}")

        if resp.type != "stream":
            raise RuntimeError(f"Expected stream DataReady, got type={resp.type}")

        channel = await self._transport.channel(resp.data_topic)
        try:
            async for msg in channel.receive():
                # Dedup by (source, sequence) — skip re-delivered messages
                if self._dedup.is_duplicate(
                    msg.headers.get(SOURCE, msg.headers.get(SOURCE_APP, "")),
                    msg.headers.get(SEQUENCE, "0"),
                ):
                    continue
                try:
                    parsed = model_type.model_validate_json(msg.payload)
                except Exception:
                    continue
                yield parsed
        finally:
            await channel.close()
