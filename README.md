# trading-sdk

Shared SDK for the trading-cz platform — batteries-included Kafka messaging,
market data models, and strategy tooling. **One `pip install`, zero boilerplate.**

## Install

```bash
pip install -e /path/to/sdk
```

Requires Python ≥ 3.14. Bring your own Kafka broker (default: `localhost:9092`).

---

## Package Structure

```
tradingcz/
├── __init__.py              # Top-level convenience re-exports
├── py.typed                 # PEP 561 marker
│
├── models/                  # 📦 Data models — the "what" of the system
│   ├── market/              #   Bar, Quote, Trade, Snapshot, OptionSnapshot
│   ├── events.py            #   DataRequest, DataReady, DataError
│   ├── headers.py           #   MessageType, Header, make_headers()
│   ├── health.py            #   ServiceLifecycle
│   ├── signal.py            #   TradingSignal
│   ├── executor/            #   🔒 FROZEN — executor event/order models
│   └── enums/               #   Timeframe, OrderSide, OrderStatus, etc.
│
├── clients/                 # 🔌 Client API — the "how to interact" layer
│   ├── data/                #   StockDataClient, OptionsDataClient, CorporateActionsClient
│   ├── positions.py         #   PositionClient
│   ├── balance.py           #   BalanceClient
│   ├── orders.py            #   OrderClient
│   └── signals.py           #   SignalPublisher
│
├── framework/               # 🏗️ Application framework
│   ├── service.py           #   ServiceApp — base class for ALL services
│   ├── trading.py           #   TradingApp — strategy/consumer role
│   ├── health.py            #   HealthPublisher, HealthMonitor
│   └── helpers.py           #   FireAndForget, RequestReply
│
├── core/                    # ⚙️ Infrastructure — transport, messaging, serialization
│   ├── transport/           #   KafkaTransport, KafkaChannel, KafkaMessage
│   ├── messaging/           #   TypedProducer, TypedConsumer, TypedParser
│   ├── topics.py            #   TopicRegistry
│   └── serialization/       #   JsonCodec, Serializer, Deserializer
│
├── common/                  # 🧰 Shared utilities — no domain knowledge
│   ├── config.py            #   KafkaSettings, LoggingSettings
│   ├── errors.py            #   SdkError hierarchy
│   ├── retry.py             #   Retry — generic async retry
│   └── registry.py          #   Registry — generic class registry
│
└── indicators/              # 📊 Technical analysis
    └── atr.py               #   calculate_atr()
```

### Where to Find Things

| If you want to... | Import from | Look for... |
|---|---|---|
| Get started quickly | `tradingcz` | `TradingApp`, `Bar`, `TradingSignal` |
| Request historical data | `tradingcz.clients.data.stock` | `StockDataClient.bars()` |
| Stream real-time quotes | `tradingcz.clients.data.stock` | `StockDataClient.quotes()` |
| Get current positions | `tradingcz.clients.positions` | `PositionClient` |
| Publish a trading signal | `tradingcz.clients.signals` | `SignalPublisher.publish()` |
| Build a custom service | `tradingcz.framework` | `ServiceApp` |
| Work with Kafka directly | `tradingcz.core.transport` | `KafkaTransport`, `KafkaChannel` |
| Serialize/deserialize | `tradingcz.core.serialization` | `JsonCodec` |
| Compute indicators | `tradingcz.indicators` | `calculate_atr()` |

---

## Quickstart — The 3-Minute Tour

### 1. Request Historical Bars

```python
import asyncio
from tradingcz import TradingApp

async def main():
    async with TradingApp(service_id="my-strategy") as app:
        # Request 30 days of 1-hour bars for AAPL and MSFT
        bars = await app.stock.bars(
            symbols=["AAPL", "MSFT"],
            days=30,
            timeframe="1h",
        )

        for symbol, history in bars.items():
            closes = [b.close for b in history]
            print(f"{symbol}: {len(history)} bars, close range "
                  f"{min(closes):.2f} – {max(closes):.2f}")

asyncio.run(main())
```

### 2. Stream Real-Time Quotes

```python
import asyncio
from tradingcz import TradingApp

async def main():
    async with TradingApp(service_id="quote-watcher") as app:
        # Stream quotes — guaranteed unsubscribe on exit
        async with app.stock.stream_quotes(["AAPL"]) as stream:
            async for stream_quote in stream:
                q = stream_quote.quote
                spread = q.ask_price - q.bid_price
                print(f"AAPL  bid={q.bid_price:.2f}  ask={q.ask_price:.2f}  "
                      f"spread={spread:.4f}")
                if spread < 0.01:
                    print("  → tight spread, opportunity?")
                    break  # exits context manager, unsubscribes automatically

asyncio.run(main())
```

### 3. Request Options Data

```python
import asyncio
from tradingcz import TradingApp

async def main():
    async with TradingApp(service_id="options-scanner") as app:
        # Get snapshots for specific option contracts
        snapshots = await app.options.snapshots([
            "AAPL260618C00250000",
            "AAPL260618P00250000",
        ])

        for symbol, snap in snapshots.items():
            print(f"{symbol}: iv={snap.implied_volatility:.4f}, "
                  f"delta={snap.delta:.4f}, gamma={snap.gamma:.4f}")

        # Get the full option chain for an underlying
        chain = await app.options.chain("AAPL")
        print(f"AAPL chain: {len(chain)} contracts")

asyncio.run(main())
```

### 4. Query Positions & Balance

```python
import asyncio
from tradingcz import TradingApp

async def main():
    async with TradingApp(service_id="risk-checker") as app:
        # Get all open positions
        positions = await app.positions.get_positions()
        for pos in positions:
            print(f"{pos.symbol}: {pos.qty} @ avg {pos.avg_entry_price:.2f}")

        # Get a specific position
        aapl = await app.positions.get_position("AAPL")
        if aapl:
            print(f"AAPL position: {aapl.qty} shares")

        # Check buying power
        balance = await app.balance.get_balance()
        print(f"Cash: ${balance.cash:,.2f}")
        print(f"Buying power: ${balance.buying_power:,.2f}")

asyncio.run(main())
```

### 5. Publish a Trading Signal

```python
import asyncio
from datetime import UTC, datetime, timedelta
from tradingcz import TradingApp, TradingSignal, calculate_atr

async def main():
    async with TradingApp(service_id="breakout-strategy") as app:
        # Get historical data for the signal logic
        bars = await app.stock.bars(["AAPL"], days=14, timeframe="1h")

        for symbol, history in bars.items():
            if not history:
                continue

            # Compute ATR for volatility-adjusted stops
            atr = calculate_atr(history, period=14)
            last_close = history[-1].close

            # Build and publish the signal
            signal = TradingSignal(
                symbol=symbol,
                side="LONG",
                strategy_id="breakout-strategy",
                open_price=last_close,
                entry_price=last_close + atr * 0.5,
                stop_loss=last_close - atr * 2.0,
                valid_until_et=datetime.now(UTC) + timedelta(hours=4),
                atr_period=14,
                atr_value=atr,
            )
            await app.signals.publish(signal, tracking_id=f"{symbol}-brk-001")
            print(f"Signal published: {symbol} LONG @ {signal.entry_price:.2f}")

asyncio.run(main())
```

### 6. Using Clients Standalone (Without TradingApp)

```python
import asyncio
from tradingcz import ServiceApp
from tradingcz.clients.positions import PositionClient
from tradingcz.clients.balance import BalanceClient
from tradingcz.clients.signals import SignalPublisher

async def main():
    async with ServiceApp(service_id="custom-service") as svc:
        # Wire up clients manually for full control
        positions = PositionClient(
            rr=svc._rr,
            transport=svc.transport,
            topics=svc.topics,
        )
        balance = BalanceClient(
            rr=svc._rr,
            transport=svc.transport,
            topics=svc.topics,
        )

        # Use them
        pos = await positions.get_position("AAPL")
        bal = await balance.get_balance()
        print(f"AAPL: {pos.qty if pos else 0} shares, Cash: ${bal.cash:,.2f}")

asyncio.run(main())
```

### 7. Building a Minimal Service

```python
import asyncio
from tradingcz import ServiceApp

async def main():
    async with ServiceApp(service_id="my-minimal-service") as svc:
        # Health/heartbeat is automatic from here
        # Events channel is ready for publishing
        # Transport is connected

        # Wait for shutdown signal (SIGTERM/SIGINT)
        await svc.wait_for_shutdown()
        print("Shutting down gracefully...")

asyncio.run(main())
```

### 8. Custom Serialization

```python
from tradingcz.core.serialization.protocol import Serializer, Deserializer, Codec
import msgpack

class MsgPackCodec(Codec[MyModel]):
    """Custom codec using MessagePack instead of JSON."""

    def __init__(self, model_type: type[MyModel]):
        self._model_type = model_type

    def serialize(self, value: MyModel) -> bytes:
        return msgpack.dumps(value.model_dump())

    def deserialize(self, data: bytes) -> MyModel:
        return self._model_type(**msgpack.loads(data))

    def content_type(self) -> str:
        return "application/msgpack"
```

### 9. Retry Pattern

```python
import asyncio
from tradingcz import Retry

async def main():
    retry = Retry(max_retries=3, delay=2.0)

    try:
        result = await retry.call(lambda: some_flaky_operation())
        print(f"Succeeded after {retry.attempts} attempt(s)")
    except Exception as e:
        print(f"Failed after {retry.attempts} attempts: {e}")

asyncio.run(main())
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker addresses (comma-separated) |
| `KAFKA_CONSUMER_GROUP` | `<service_id>` | Consumer group ID for offset management |
| `SDK_ENV` | `dev` | Deployment environment (`dev` / `prod`) |
| `SDK_HEALTH_INTERVAL` | `300` | Heartbeat interval in seconds |
| `SDK_BROKER` | `alpaca` | Broker identifier (TradingApp only) |

## Feature Flags

Disable clients you don't need to reduce resource usage:

```python
app = TradingApp(service_id="risk-checker")
app.with_signals(False).with_data(False)
# Only app.positions, app.balance, app.orders are available
```

---

## SDK Philosophy

The SDK is the **source of truth** for the trading-cz platform. Every service
shares these concepts through the SDK:

- **Data models** — what a Bar, Quote, Trade, Signal, or Order looks like on the wire
- **Wire protocol** — how messages are enveloped, routed, correlated, and versioned
- **Transport** — how bytes move between services (Kafka topics, partitions, serialization)
- **Client patterns** — how to request data, stream data, publish signals, query state

No other repository defines its own message format, serialization, or topic naming.
If two services disagree on the wire format, the SDK is the arbiter.

### Design Principles

1. **Top-level is for beginners.** `from tradingcz import TradingApp, Bar` covers 80% of use cases.

2. **Folders describe their contents.** `models/` has models. `clients/` has clients. No surprises.

3. **Open for extension.** Pre-1.0, every module is importable and subclassable. No `_` prefix barriers.

4. **One obvious way.** Each concept has one clear import path.

---

## Unit Tests — Required for All Public APIs

Every public symbol MUST have unit tests. The SDK is the **wire protocol
authority** — if its models or headers are wrong, every downstream service
(simple-strategy, ingestion, risk, executor) breaks silently.

### What Must Be Tested

| Layer | What to test | Example |
|-------|-------------|---------|
| **Models** | Round-trip JSON serialization | `Bar.model_validate_json(bar.model_dump_json()) == bar` |
| **Models** | Field validation rejects bad data | `Bar(symbol=123)` → raises `ValidationError` |
| **Headers** | `make_headers()` output is correct | `make_headers(message_type="bar")` → contains `message_type`, `source_app`, `sequence` |
| **Headers** | `parse_message()` deserializes correctly | `parse_message(MessageType.DATA_READY, payload)` → `DataReady` instance |
| **Headers** | `build_event_key()` is deterministic | Same inputs → same key string |
| **Configuration** | `TopicRegistry` names are environment-scoped | `TopicRegistry(env="dev").events.name == "dev-event"` |
| **Configuration** | `ServiceSettings` loads from env vars | `SDK_ENV=tst` → `settings.env == "tst"` |

### How to Write SDK Unit Tests

```python
# tests/unit/test_bar_model.py
from tradingcz.model.ingestion.bar import Bar
from datetime import datetime, timezone

def test_bar_roundtrip():
    """Bar survives JSON serialize → deserialize cycle."""
    bar = Bar(
        symbol="SPY",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        open=100.0, high=101.0, low=99.0, close=100.5,
        volume=1_000_000.0,
    )
    json_str = bar.model_dump_json()
    parsed = Bar.model_validate_json(json_str)
    assert parsed == bar

def test_bar_rejects_invalid_symbol_type():
    """Bar symbol must be a string."""
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Bar(symbol=123, timestamp=..., open=0, high=0, low=0, close=0, volume=0)
```

### Why Unit Tests Are Non-Negotiable

The testing repo (`trading-cz/testing`) uses the SDK as a **tool** to:
- Build correct Kafka headers via `make_headers()`
- Serialize messages via `Bar.model_dump_json()`, `DataReady(...)`, etc.
- Validate received messages via `TradingSignal.model_validate_json(msg)`

If the SDK's wire format is broken, the testing repo **cannot detect it** — it
trusts the SDK. The safety net is the SDK's own unit test suite, which must
pass on every PR.

**Rule**: No SDK PR merges without green CI (pytest + mypy + ruff).

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Type check
mypy tradingcz/

# Lint & format
ruff check tradingcz/
ruff format tradingcz/
```

## See Also

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — module map, design decisions, transport layer details
- **[docs/python314.md](docs/python314.md)** — modern Python 3.14 patterns used in this codebase
- **[structure.md](structure.md)** — proposed future layout (in development)

