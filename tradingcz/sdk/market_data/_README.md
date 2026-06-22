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

All clients share a single ``BaseDataClient`` instance (one per broker scope).
``BaseDataClient`` is created automatically by :class:`~tradingcz.sdk.service_app.ServiceApp`
— you never instantiate it directly in application code.

---

## Recommended Usage — via ServiceApp

:class:`~tradingcz.sdk.service_app.ServiceApp` is the standard base class for all
trading services.  It wires Kafka transport, health publishing, and market data
clients together.  Clients are created **lazily** on first access.

```python
import asyncio
from tradingcz.sdk.service_app import ServiceApp
from tradingcz.sdk.transport.kafka_settings import KafkaSettings

async def main():
    # 1. Construct — pass service identity + Kafka connection
    app = ServiceApp(
        service_id="my-strategy",
        env="dev",
        kafka_settings=KafkaSettings(),  # reads KAFKA_BOOTSTRAP_SERVERS from env
    )

    # 2. Start — creates topics, connects Kafka, health → READY
    await app.start()

    try:
        # 3. Use clients (all created lazily on first access)
        bars = await app.stock.bars(["AAPL"], days=30, timeframe="1Hour")
        quotes = await app.stock.latest_quotes(["AAPL"])

        async with app.stock_stream.stream_quotes(["AAPL"]) as stream:
            async for quote in stream:
                if quote.bid_price > 100:
                    break

    finally:
        # 4. Close — health → DOWN, flush producers, close connections
        await app.close()

asyncio.run(main())
```

**Async context manager** (auto start/close):

```python
async with ServiceApp(service_id="my-strategy", env="dev",
                      kafka_settings=KafkaSettings()) as app:
    bars = await app.stock.bars(["AAPL"], days=30, timeframe="1Hour")
    # close() called automatically on exit
```

**Lifecycle**: ``__init__()`` → ``start()`` → *use clients* → ``close()``

| Step | What happens |
|------|-------------|
| ``__init__()`` | Stores config, creates ``KafkaTopicRegistry``, ``TransportProducer``, ``HealthPublisher`` |
| ``start()`` | Ensures topics exist, starts ``RequestReply``, creates ``BaseDataClient``, health → ``READY`` |
| ``close()`` | Health → ``DOWN``, closes ``RequestReply``, flushes producer |

---

## StockDataClient — historic & latest data

**Constructor**: ``StockDataClient(base: BaseDataClient)`` — created by ``ServiceApp``, not directly.

**Access**: ``app.stock`` (lazy property on ``ServiceApp``).

```python
async with ServiceApp(service_id="my-strategy", env="dev",
                      kafka_settings=KafkaSettings()) as app:

    # ── Historical bars ──────────────────────────────────────────
    bars: dict[str, list[Bar]] = await app.stock.bars(
        ["AAPL", "MSFT"],
        days=30,
        timeframe="1Hour",       # or Timeframe.H1
        timeout=30.0,            # seconds (default: 30)
    )

    # ── Latest snapshots (poll-friendly, no streaming) ───────────
    quote: dict[str, Quote] = await app.stock.latest_quotes(
        ["AAPL"],
        timeout=5.0,             # seconds (default: 5)
    )

    trade: dict[str, Trade] = await app.stock.latest_trades(
        ["AAPL"],
        timeout=5.0,
    )

    bar: dict[str, Bar] = await app.stock.latest_bars(
        ["AAPL"],
        timeout=5.0,
    )
```

---

## StockStreamClient — live streaming data

**Constructor**: ``StockStreamClient(base: BaseDataClient)`` — created by ``ServiceApp``, not directly.

**Access**: ``app.stock_stream`` (lazy property on ``ServiceApp``).

All streaming methods return a :class:`StreamHandle[T]` which supports
**two patterns**:

### Pattern 1: Context manager (recommended)

Unsubscribe is sent on exit — even if an exception is raised.

```python
async with ServiceApp(service_id="my-strategy", env="dev",
                      kafka_settings=KafkaSettings()) as app:

    async with app.stock_stream.stream_quotes(
        ["AAPL"],
        timeout=30.0,            # seconds (default: 30)
    ) as stream:
        async for quote in stream:
            # quote is a Quote — bid_price, ask_price, timestamp…
            print(f"{quote.symbol} bid={quote.bid_price} ask={quote.ask_price}")
            if quote.bid_price > threshold:
                break
    # ← unsubscribe sent here, even on exception

    # ── Stream bars ──────────────────────────────────────────────
    async with app.stock_stream.stream_bars(
        ["AAPL"],
        timeframe=Timeframe.H4,  # default: H4
        timeout=30.0,
    ) as stream:
        async for bar in stream:
            print(f"{bar.symbol} close={bar.close} volume={bar.volume}")

    # ── Stream trades ────────────────────────────────────────────
    async with app.stock_stream.stream_trades(
        ["AAPL"],
        timeout=30.0,
    ) as stream:
        async for trade in stream:
            print(f"{trade.symbol} price={trade.price} size={trade.size}")
```

### Pattern 2: Bare iteration (cleanup on loop exit)

```python
async for quote in app.stock_stream.stream_quotes(["AAPL"]):
    if done:
        break  # channel is closed when the async generator is garbage-collected
```

> **Prefer the context manager.**  Bare iteration may not send an explicit
> unsubscribe, leaving the ingestion service streaming data until the
> consumer disconnects.

---

## OptionsHistoricDataClient — option snapshots

**Constructor**: ``OptionsHistoricDataClient(base: BaseDataClient)`` — created by ``ServiceApp``, not directly.

**Access**: ``app.options`` (lazy property on ``ServiceApp``).

```python
async with ServiceApp(service_id="my-strategy", env="dev",
                      kafka_settings=KafkaSettings()) as app:

    snapshots: dict[str, list[OptionSnapshot]] = await app.options.snapshots(
        ["AAPL250620C00150000"],
        timeout=30.0,
    )
    for symbol, snaps in snapshots.items():
        for s in snaps:
            print(f"{symbol} bid={s.quote.bid_price} iv={s.greeks.iv}")
```

---

## CorporateActionsClient — dividends & splits

**Constructor**: ``CorporateActionsClient(base: BaseDataClient)`` — created by ``ServiceApp``, not directly.

**Access**: ``app.corporate_actions`` (lazy property on ``ServiceApp``).

```python
async with ServiceApp(service_id="my-strategy", env="dev",
                      kafka_settings=KafkaSettings()) as app:

    dividends = await app.corporate_actions.dividends(["AAPL"], days=365)
    splits = await app.corporate_actions.splits(["AAPL"], days=365)
```

---

## TimeKeeper — market clock

**Constructor**: ``TimeKeeper(trading_client)`` — standalone, no ``ServiceApp`` needed.

```python
from tradingcz.sdk.market_data import TimeKeeper

clock = TimeKeeper(trading_client)
await clock.start_timekeeping()

# Emits pre-close warning events before market close.
# Strategies use this to wind down positions before the session ends.
```

---

## Direct Construction (advanced)

If you can't use ``ServiceApp``, you can wire clients manually.
This is uncommon — prefer ``ServiceApp`` unless you have a specific reason.

```python
from tradingcz.sdk.market_data._base import BaseDataClient
from tradingcz.sdk.market_data.stock_historic import StockDataClient
from tradingcz.sdk.market_data.stock_stream import StockStreamClient
from tradingcz.sdk.messaging.request_reply import RequestReply
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.transport.kafka_topic import KafkaTopicAdmin, KafkaTopicRegistry
from tradingcz.sdk.transport.transport_producer import TransportProducer

settings = KafkaSettings()
topics = KafkaTopicRegistry(env="dev")
producer = TransportProducer(settings)

# Ensure topics exist
admin = KafkaTopicAdmin(settings)
await admin.ensure_from_config(topics.events)

# Start RequestReply (handles DataRequest → DataReady handshake)
rr = RequestReply(
    producer=producer,
    topic=topics.events.name,
    settings=settings,
    service_id="my-strategy",
    group_suffix="svc-reply",
)
await rr.start()

# Create BaseDataClient (shared by all market data clients)
base = BaseDataClient(
    rr=rr,
    settings=settings,
    topics=topics,
    service_id="my-strategy",
)

# Create clients
stock = StockDataClient(base)
stock_stream = StockStreamClient(base)

# Use them…
bars = await stock.bars(["AAPL"], days=30, timeframe="1Hour")

async with stock_stream.stream_quotes(["AAPL"]) as stream:
    async for quote in stream:
        break

# Teardown
await rr.close()
await producer.close()
await admin.close()
```

> This is roughly what ``ServiceApp.start()`` / ``ServiceApp.close()`` do for you.
> Use direct construction only when you need fine-grained control over the transport layer.
```
