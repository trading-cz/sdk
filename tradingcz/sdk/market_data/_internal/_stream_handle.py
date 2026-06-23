"""StreamHandle — async context manager for guaranteed unsubscribe."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from types import TracebackType

from tradingcz.sdk.messaging.fire_and_forget import FireAndForget
from tradingcz.sdk.models.enums.event import (
    AssetType,
    Broker,
    DataRequestType,
    MarketDataType,
)
from tradingcz.sdk.models.events import DataRequest
from tradingcz.sdk.typed.typed_producer import TypedProducer

logger = logging.getLogger(__name__)


class StreamHandle[T](AsyncIterator[T]):
    """Handle to a live data stream with automatic cleanup.  """

    def __init__(self, iterator: AsyncIterator[T], unsubscribe: _Unsubscribe, ) -> None:
        self._iterator = iterator
        self._unsubscribe = unsubscribe
        self._exited = False

    def __aiter__(self) -> StreamHandle[T]:
        return self

    async def __anext__(self) -> T:
        try:
            return await self._iterator.__anext__()
        except StopAsyncIteration:
            self._exited = True
            raise

    async def __aenter__(self) -> StreamHandle[T]:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None) -> None:
        self._exited = True
        try:
            await self._unsubscribe()
        except Exception:
            logger.info("Unsubscribe failed (non-critical)", exc_info=True)
        if hasattr(self._iterator, "aclose"):
            await self._iterator.aclose()  # type: ignore[union-attr]


class _Unsubscribe:
    """Fire-and-forget unsubscribe — sends a DataRequest, no response expected."""

    def __init__(
        self,
        producer: TypedProducer,
        service_id: str,
        broker: Broker,
        symbols: list[str],
        data_kind: MarketDataType,
        asset: AssetType,
    ) -> None:
        self._faf = FireAndForget(producer, service_id)
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
        try:
            await self._faf.send(req, event_id=str(req.event_id))
        except Exception:
            logger.info("Unsubscribe request failed for %s (data_kind=%s)", self._symbols, self._data_type, exc_info=True)


__all__ = ["StreamHandle"]
