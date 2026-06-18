"""BaseDataClient — internal shared transport logic for all market data clients.

Application code never references this module directly.  Use
``StockDataClient``, ``OptionsDataClient``, or ``CorporateActionsClient``
via ``TradingApp``.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import TracebackType

from tradingcz.sdk.transport.topics import TopicRegistry
from tradingcz.sdk.transport.dedup import DedupFilter
from tradingcz.sdk.transport.transport import KafkaTransport
from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.models.enums.event import EventType, MarketDataType, DataRequestType
from tradingcz.sdk.models.events import DataError, DataReady, DataRequest
from tradingcz.sdk.models.headers import Header

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# StreamHandle — async context manager for guaranteed unsubscribe
# ------------------------------------------------------------------


class StreamHandle[T](AsyncIterator[T]):
    """Handle to a live data stream with automatic cleanup.

    A :class:`StreamHandle` is returned by streaming methods like
    ``app.stock.stream_quotes()`` and ``app.stock.stream_trades()``.  It can be used
    in two ways:

    **Bare iteration** (cleanup on loop exit)::

        async for quote in app.stock.stream_quotes(["AAPL"]):
            if done:
                break  # channel is closed automatically

    **Context manager** (guaranteed unsubscribe via DataRequest)::

        async with app.stock.stream_quotes(["AAPL"]) as stream:
            async for quote in stream:
                ...
        # unsubscribe sent here, even if exception raised

    The context-manager form sends an explicit ``unsubscribe``
    ``DataRequest`` on exit, allowing the ingestion service to stop
    pushing data for these symbols.
    """

    def __init__(
        self,
        iterator: AsyncIterator[T],
        unsubscribe: _Unsubscribe | None = None,
    ) -> None:
        self._iterator = iterator
        self._unsubscribe = unsubscribe
        self._exited = False

    def __aiter__(self) -> "StreamHandle[T]":
        return self

    async def __anext__(self) -> T:
        try:
            return await self._iterator.__anext__()
        except StopAsyncIteration:
            self._exited = True
            raise

    async def __aenter__(self) -> "StreamHandle[T]":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._exited = True
        if self._unsubscribe is not None:
            try:
                await self._unsubscribe()
            except Exception:
                logger.debug("Unsubscribe failed (non-critical)", exc_info=True)
        # Close the underlying async generator
        if hasattr(self._iterator, "aclose"):
            await self._iterator.aclose()  # type: ignore[union-attr]


class _Unsubscribe:
    """Callable that sends an unsubscribe DataRequest."""

    def __init__(
        self,
        rr: RequestReply,
        broker: str,
        symbols: list[str],
        data_kind: MarketDataType,
        asset: str,
    ) -> None:
        self._rr = rr
        self._broker = broker
        self._symbols = symbols
        self._data_type = data_kind
        self._asset = asset

    async def __call__(self) -> None:
        """Send unsubscribe DataRequest (fire-and-forget)."""
        req = DataRequest(
            type=DataRequestType.UNSUBSCRIBE,
            asset=self._asset,
            broker=self._broker,
            symbols=self._symbols,
            data_type=self._data_type,
        )
        # Fire-and-forget — no response expected for unsubscribe
        self._rr.register_type(EventType.DATA_READY, DataReady)
        self._rr.register_type(EventType.DATA_ERROR, DataError)
        try:
            await self._rr.request(
                req,
                response_type=DataReady,
                request_type=EventType.DATA_REQUEST,
                timeout=5.0,
            )
        except Exception:
            logger.debug(
                "Unsubscribe request failed for %s (data_kind=%s)",
                self._symbols,
                self._data_type,
                exc_info=True,
            )


# ------------------------------------------------------------------
# BaseDataClient — shared transport logic
# ------------------------------------------------------------------


class BaseDataClient:
    """Internal: shared request/reply + typed consumption for all data clients.

    Concrete clients (``StockDataClient``, ``OptionsDataClient``, etc.)
    receive an instance of this class and call its internal methods.
    Application code never references ``BaseDataClient`` directly.

    One ``BaseDataClient`` is created per broker scope inside
    ``TradingApp.start()`` and shared by all data clients that use
    the same broker.
    """

    def __init__(
        self,
        rr: RequestReply,
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
        rr.register_type(EventType.DATA_READY, DataReady)
        rr.register_type(EventType.DATA_ERROR, DataError)

    # -- Historical (request → consume → return dict) ------------------

    async def _request_historical[
        T
    ](  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        symbols: list[str],
        asset: str,
        data_kind: MarketDataType,
        model_type: type[T],
        *,
        timeframe: str | None = None,
        days: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        timeout: float = 30.0,
    ) -> dict[str, list[T]]:
        """Send DataRequest for historical data, consume typed results.

        Returns ``{symbol: [T sorted by timestamp]}``.
        """
        start: datetime | None
        end: datetime | None
        if start_time is None and days is not None:
            end = end_time or datetime.now(UTC)
            start = end - timedelta(days=days)
        else:
            start = start_time
            end = end_time

        req = DataRequest(
            type=DataRequestType.HISTORIC,
            asset=asset,
            broker=self._broker,
            symbols=symbols,
            data_type=data_kind,
            timeframe=timeframe or "1d",
            start_time=start,
            end_time=end,
        )

        resp = await self._rr.request(
            req,
            response_type=DataReady,
            request_type=EventType.DATA_REQUEST,
            timeout=timeout,
        )

        if resp.event_type == EventType.DATA_ERROR:
            raise RuntimeError(f"DataError from ingestion: {resp.error}")
        if resp.type != DataRequestType.HISTORIC:
            raise RuntimeError(f"Expected historic DataReady, got type={resp.type}")

        logger.info(
            "DataReady(historic): topic=%s record_count=%s",
            resp.data_topic,
            resp.record_count,
        )

        channel = await self._transport.channel(resp.data_topic)
        results: dict[str, list[T]] = {}
        count = 0
        expected = resp.record_count or 0

        try:
            async for msg in channel.receive():
                if msg.headers.get(Header.EVENT_ID) != req.event_id:
                    continue
                seq = msg.headers.get(Header.SEQUENCE, "")
                if seq and self._dedup.is_duplicate(
                    msg.headers.get(Header.SOURCE, msg.headers.get(Header.SOURCE_APP, "")),
                    seq,
                ):
                    continue
                try:
                    item = model_type.model_validate_json(msg.payload)  # type: ignore[attr-defined]
                except Exception:  # pylint: disable=broad-exception-caught
                    logger.debug("Skipping unparseable %s", data_kind, exc_info=True)
                    continue
                results.setdefault(item.symbol, []).append(item)  # type: ignore[union-attr]
                count += 1
                if expected and count >= expected:
                    break
        finally:
            await channel.close()

        for symbol_items in results.values():
            symbol_items.sort(key=lambda b: b.timestamp)  # type: ignore[attr-defined]

        return results

    # -- Streaming (subscribe → yield indefinitely → unsubscribe) ------

    async def _stream[
        T
    ](  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        symbols: list[str],
        asset: str,
        data_kind: MarketDataType,
        model_type: type[T],
        *,
        timeout: float = 30.0,
    ) -> StreamHandle[T]:
        """Send DataRequest for streaming, return a :class:`StreamHandle`.

        The returned handle supports both bare ``async for`` iteration
        and ``async with`` context-manager usage (recommended for
        guaranteed unsubscribe).
        """
        req = DataRequest(
            type=DataRequestType.STREAM,
            asset=asset,
            broker=self._broker,
            symbols=symbols,
            data_type=data_kind,
        )

        resp = await self._rr.request(
            req,
            response_type=DataReady,
            request_type=EventType.DATA_REQUEST,
            timeout=timeout,
        )

        if resp.event_type == EventType.DATA_ERROR:
            raise RuntimeError(f"DataError from ingestion (stream): {resp.error}")
        if resp.type != DataRequestType.STREAM:
            raise RuntimeError(f"Expected stream DataReady, got type={resp.type}")

        channel = await self._transport.channel(resp.data_topic)

        async def _consume() -> AsyncIterator[T]:
            try:
                async for msg in channel.receive():
                    seq = msg.headers.get(Header.SEQUENCE, "")
                    if seq and self._dedup.is_duplicate(
                        msg.headers.get(Header.SOURCE, msg.headers.get(Header.SOURCE_APP, "")),
                        seq,
                    ):
                        continue
                    try:
                        parsed = model_type.model_validate_json(msg.payload)  # type: ignore[attr-defined]
                    except Exception:
                        continue
                    yield parsed
            finally:
                await channel.close()

        unsubscribe = _Unsubscribe(
            rr=self._rr,
            broker=self._broker,
            symbols=symbols,
            data_kind=data_kind,
            asset=asset,
        )

        return StreamHandle(iterator=_consume(), unsubscribe=unsubscribe)


__all__ = ["BaseDataClient", "StreamHandle"]
