# market_data — Data Clients

Historical and streaming market data via request/reply over Kafka.

## Architecture

```text
StockDataClient / StockStreamClient / OptionsHistoricDataClient / CorporateActionsClient
            │
     BaseDataClient          ← shared transport logic (Kafka request/reply + typed consumption)
       │        │
  RequestReply  KafkaTransport
```

All clients share a single ``BaseDataClient`` instance.
``BaseDataClient`` handles the Kafka request/reply handshake and typed
message consumption — you create it once and pass it to every client.

---

## Setup — BaseDataClient

Every market data client takes a :class:`BaseDataClient` as its only
constructor argument.  Set it up once:

```python
from tradingcz.sdk.market_data._base import BaseDataClient
from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.kafka_topic import KafkaTopicAdmin, KafkaTopicRegistry
from tradingcz.sdk.transport.transport_producer import TransportProducer

settings = KafkaSettings()                      # reads KAFKA_BOOTSTRAP_SERVERS from env
topics = KafkaTopicRegistry(env="dev")
producer = TransportProducer(settings)

# Ensure the events topic exists
admin = KafkaTopicAdmin(settings)
await admin.ensure_from_config(topics.events)

# RequestReply handles DataRequest → DataReady handshake
rr = RequestReply(
    producer=producer,
    topic=topics.events.name,
    settings=settings,
    service_id="my-service",
    group_suffix="svc-reply",
)
await rr.start()

# BaseDataClient — shared by all market data clients
base = BaseDataClient(
    rr=rr,
    settings=settings,
    topics=topics,
    service_id="my-service",
)
```

**Teardown** (when done with all clients):

```python
await rr.close()
await producer.close()
await admin.close()
```

---

## StockDataClient — historic & latest data

**File**: ``stock_historic.py``  
**Constructor**: ``StockDataClient(base: BaseDataClient)``

```python
from tradingcz.sdk.market_data.stock_historic import StockDataClient

stock = StockDataClient(base)

# ── Historical bars ──────────────────────────────────────────
bars: dict[str, list[Bar]] = await stock.bars(
    ["AAPL", "MSFT"],
    days=30,
    timeframe="1Hour",       # or Timeframe.H1
    timeout=30.0,            # seconds (default: 30)
)

# ── Latest snapshots (poll-friendly, no streaming) ───────────
quotes: dict[str, Quote] = await stock.latest_quotes(
    ["AAPL"],
    timeout=5.0,             # seconds (default: 5)
)

trades: dict[str, Trade] = await stock.latest_trades(
    ["AAPL"],
    timeout=5.0,
)

bars: dict[str, Bar] = await stock.latest_bars(
    ["AAPL"],
    timeout=5.0,
)
```

| Method | Returns | Description |
|--------|---------|-------------|
| ``bars(symbols, *, days, timeframe, timeout)`` | ``dict[str, list[Bar]]`` | Historical OHLCV bars |
| ``latest_quotes(symbols, *, timeout)`` | ``dict[str, Quote]`` | Most recent quote per symbol |
| ``latest_trades(symbols, *, timeout)`` | ``dict[str, Trade]`` | Most recent trade per symbol |
| ``latest_bars(symbols, *, timeout)`` | ``dict[str, Bar]`` | Most recent minute bar per symbol |

---

## StockStreamClient — live streaming data

**File**: ``stock_stream.py``  
**Constructor**: ``StockStreamClient(base: BaseDataClient)``

```python
from tradingcz.sdk.market_data.stock_stream import StockStreamClient

stream = StockStreamClient(base)
```

All streaming methods return a :class:`StreamHandle[T]` which supports
**two usage patterns**:

### Pattern 1: Context manager (recommended)

Unsubscribe is sent on exit — even if an exception is raised.

```python
async with stream.stream_quotes(
    ["AAPL"],
    timeout=30.0,            # seconds (default: 30)
) as quotes:
    async for quote in quotes:
        # quote is a Quote — bid_price, ask_price, timestamp…
        print(f"{quote.symbol} bid={quote.bid_price} ask={quote.ask_price}")
        if quote.bid_price > threshold:
            break
# ← unsubscribe sent here, even on exception

async with stream.stream_bars(
    ["AAPL"],
    timeframe=Timeframe.H4,  # default: H4
    timeout=30.0,
) as bars:
    async for bar in bars:
        print(f"{bar.symbol} close={bar.close} volume={bar.volume}")

async with stream.stream_trades(
    ["AAPL"],
    timeout=30.0,
) as trades:
    async for trade in trades:
        print(f"{trade.symbol} price={trade.price} size={trade.size}")
```

### Pattern 2: Bare iteration

Channel is closed when the async generator is garbage-collected.

```python
async for quote in stream.stream_quotes(["AAPL"]):
    if done:
        break
```

> **Prefer the context manager.**  Bare iteration may not send an explicit
> unsubscribe, leaving the ingestion service streaming data until the
> consumer disconnects.

| Method | Returns | Description |
|--------|---------|-------------|
| ``stream_quotes(symbols, *, timeout)`` | ``StreamHandle[Quote]`` | Live bid/ask quotes |
| ``stream_bars(symbols, *, timeframe, timeout)`` | ``StreamHandle[Bar]`` | Live bar closes (OHLCV) |
| ``stream_trades(symbols, *, timeout)`` | ``StreamHandle[Trade]`` | Live trade ticks |

---

## OptionsHistoricDataClient — option snapshots

**File**: ``option_historic.py``  
**Constructor**: ``OptionsHistoricDataClient(base: BaseDataClient)``

```python
from tradingcz.sdk.market_data.option_historic import OptionsHistoricDataClient

options = OptionsHistoricDataClient(base)

snapshots: dict[str, list[OptionSnapshot]] = await options.snapshots(
    ["AAPL250620C00150000"],
    timeout=30.0,
)
for symbol, snaps in snapshots.items():
    for s in snaps:
        print(f"{symbol} bid={s.quote.bid_price} iv={s.greeks.iv}")
```

| Method | Returns | Description |
|--------|---------|-------------|
| ``snapshots(symbols, *, timeout)`` | ``dict[str, list[OptionSnapshot]]`` | Trade, quote, greeks, IV per contract |

---

## CorporateActionsClient — dividends & splits

**File**: ``corporate.py``  
**Constructor**: ``CorporateActionsClient(base: BaseDataClient)``

```python
from tradingcz.sdk.market_data.corporate import CorporateActionsClient

corp = CorporateActionsClient(base)

dividends = await corp.dividends(["AAPL"], days=365)
splits = await corp.splits(["AAPL"], days=365)
```

| Method | Returns | Description |
|--------|---------|-------------|
| ``dividends(symbols, *, days, timeout)`` | ``dict[str, list[Dividend]]`` | Historical dividend payments |
| ``splits(symbols, *, days, timeout)`` | ``dict[str, list[StockSplit]]`` | Historical stock splits |

---

## TimeKeeper — market clock

**File**: ``clock.py``  
**Constructor**: ``TimeKeeper(trading_client)`` — standalone, no ``BaseDataClient`` needed.

```python
from tradingcz.sdk.market_data import TimeKeeper

clock = TimeKeeper(trading_client)
await clock.start_timekeeping()

# Emits pre-close warning events before market close.
# Strategies use this to wind down positions before the session ends.
```
