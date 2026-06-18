# trading-sdk

Shared SDK for the trading-cz platform — typed Kafka messaging, market data clients, and strategy tooling.

## Structure

```
tradingcz/sdk/
├── service_app.py       # ServiceApp — base for ALL services (transport, health, shutdown)
├── trading_app.py       # TradingApp — batteries-included strategy entry point
├── exceptions.py        # SdkError hierarchy
├── logging.py           # setup_logging(), LokiJSONFormatter
│
├── market_data/         # StockDataClient, OptionsDataClient, CorporateActionsClient, TimeKeeper
├── account/             # BalanceClient, OrderClient, PositionClient, SignalPublisher
├── health/              # HealthMonitor — track other services' liveness
├── indicators/          # Technical indicators (calculate_atr, …)
├── lang/                # Registry, Retry — language-level utilities
│
├── models/              # Pydantic models — enums, events, market data, orders
├── transport/           # KafkaChannel, KafkaTransport, KafkaSettings (internal)
├── messaging/           # TypedProducer/Consumer, RequestReply, EventRouter, FireAndForget
└── serialization/       # JsonCodec, JsonSerializer, Serializer/Deserializer protocol
```

## Quickstart

### Strategy (consume data, publish signals)

```python
from tradingcz.sdk import TradingApp
from tradingcz.sdk.market_data import StockDataClient
from tradingcz.sdk.indicators import calculate_atr

async with TradingApp(service_id="my-strategy") as app:
    # Historical data
    bars = await app.stock.bars(["AAPL"], days=30)

    # Streaming (context manager = guaranteed unsubscribe)
    async with app.stock.stream_quotes(["AAPL"]) as stream:
        async for quote in stream:
            ...

    # Account state
    balance = await app.balance.get_balance()
    positions = await app.positions.get_positions()

    # Publish signal
    await app.signals.publish(signal, event_id="abc-123")
```

### Provider (ingestion, executor)

```python
import asyncio
from tradingcz.sdk import ServiceApp
from tradingcz.sdk.health import HealthMonitor
from tradingcz.sdk.messaging import EventRouter
from tradingcz.sdk.models.events import DataRequest, DataResponse
from tradingcz.sdk.models.enums.event import EventType
from tradingcz.sdk.transport.message import KafkaMessage


async def my_handler(request: DataRequest, raw: KafkaMessage) -> None:
    """Process a DataRequest and publish a DataResponse."""
    source_app = raw.headers.get("source_app", "(unknown)")
    print(f"Received {request.request_id} from {source_app} "
          f"for symbols={request.symbols}")

    # ... fetch data, compute ...

    # Publish response via the service app
    response = DataResponse(
        request_id=request.request_id,
        symbols=request.symbols,
        bars=[],  # your data here
    )
    # Usually you'd call: await svc.publish_event(response, ...)


async with ServiceApp(service_id="ingestion", env="dev", health_interval=300) as svc:
    router = EventRouter(svc.events_channel)
    router.on(EventType.DATA_REQUEST, DataRequest, handler=my_handler)
    await router.run()
```

### EventRouter — Commit Modes

Every message from `KafkaChannel.receive()` carries a `commit()` method.
Choose how offsets are committed:

**Mode 1 — Router auto-commit (default, recommended)**

The router commits the offset after the handler returns successfully.
If the handler raises, the offset is **not** committed — the message
will be re-delivered on restart (at-least-once).

```python
router = EventRouter(channel, auto_commit=True)  # default

@router.on(EventType.TRADING_SIGNAL, TradingSignal, spawn_task=True)
async def on_signal(model, raw):
    await place_order(model)
    # raw.commit() called automatically by router after return.
```

For cleanest semantics, disable librdkafka's background auto-commit
(which fires on a timer regardless of handler outcome):

```bash
export KAFKA_CONSUMER_OVERRIDES='{"enable.auto.commit": "false"}'
```

**Mode 2 — Manual commit (handler controls exactly when)**

Use this when the commit must happen ONLY after a side effect succeeds:

```python
router = EventRouter(channel, auto_commit=False)

@router.on(EventType.EXECUTION_REQUEST, ExecutionRequestEvent)
async def on_request(model, raw):
    await db.save(model)        # persist first
    await raw.commit()          # commit offset AFTER DB write
    await submit_to_broker(model)  # fire-and-forget — safe to lose
```

**Mode 3 — Kafka-managed (librdkafka background auto-commit)**

The legacy behaviour — librdkafka commits periodically (~5 s)
regardless of handler outcome.  No delivery guarantee:

```python
router = EventRouter(channel, auto_commit=False)
# librdkafka auto-commit is enabled by default in KafkaSettings.
# Offsets drift forward on a timer — handler may not have finished.
```

**Error notification — `on_error`**

Catch undispatchable messages (bad JSON, unknown event type):

```python
async def log_bad_message(raw: KafkaMessage) -> None:
    logger.error("Cannot dispatch: offset=%d payload=%r",
                 raw.offset, raw.payload[:200])

router = EventRouter(channel, on_error=log_bad_message)
```

## Install

Requires **Python ≥ 3.14**, Kafka broker (default: `localhost:9092`).

```bash
# Install from GitHub release tag
pip install "trading-sdk @ git+https://github.com/trading-cz/sdk@v0.1.7"

# Uninstall
pip uninstall trading-sdk

# Or add to pyproject.toml dependencies:
#   "trading-sdk @ git+https://github.com/trading-cz/sdk@v0.1.7",

# Dev (editable install from local checkout)
pip install -e /path/to/sdk
```
