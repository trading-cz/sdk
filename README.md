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
from tradingcz.sdk import ServiceApp
from tradingcz.sdk.health import HealthMonitor
from tradingcz.sdk.messaging import EventRouter, TypedProducer

async with ServiceApp(service_id="ingestion") as svc:
    router = EventRouter(svc.events_channel)
    router.on(EventType.DATA_REQUEST, DataRequest, handler=my_handler)
    await router.run()
```

## Install

```bash
pip install trading-sdk
# or dev:
pip install -e /path/to/sdk
```

Requires Python ≥ 3.12, Kafka broker (default: `localhost:9092`).
