# trading-sdk

Shared SDK for the trading platform — batteries-included Kafka messaging,
market data models, and strategy tooling.  **One `pip install`, zero boilerplate.**

## Install

```bash
pip install -e /path/to/sdk
```

Requires Python ≥ 3.14.  Bring your own Kafka broker (default: `localhost:9092`).

## Quickstart — publish a trading signal

```python
import asyncio
from datetime import UTC, datetime
from tradingcz.sdk import TradingApp
from tradingcz.model.signal import TradingSignal

async def main():
    async with TradingApp(service_id="my-strategy") as app:
        signal = TradingSignal(
            symbol="AAPL",
            side="LONG",
            open_price=150.0,
            entry_price=151.0,
            stop_loss=149.0,
            valid_until_et=datetime(2026, 6, 1, tzinfo=UTC),
            atr_value=2.5,
        )
        await app.signals.publish(signal, tracking_id="trk-001")

asyncio.run(main())
```

## Quickstart — request historical data

```python
async with TradingApp(service_id="my-strategy") as app:
    bars = await app.data.request_historical(["AAPL", "MSFT"], days=30)
    for symbol, daily_bars in bars.items():
        print(f"{symbol}: {len(daily_bars)} bars")
```

## Quickstart — minimal service (no strategy features)

```python
from tradingcz.sdk import ServiceApp

async with ServiceApp(service_id="my-service") as svc:
    # transport, events_channel, and health/heartbeat are ready
    await svc.events_channel.send(b"hello", key="greeting")
    await svc.wait_for_shutdown()   # blocks until SIGTERM
```

## Environment variables

| Variable                  | Default          | Description                         |
|---------------------------|------------------|-------------------------------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker addresses              |
| `KAFKA_CONSUMER_GROUP`    | `<service_id>`   | Consumer group id                   |
| `SDK_ENV`                 | `dev`            | Deployment environment              |
| `SDK_HEALTH_INTERVAL`     | `300`            | Heartbeat interval (seconds)        |
| `SDK_BROKER`              | `alpaca`         | Broker identifier (TradingApp only) |

## Feature flags

Disable clients you don't need to reduce resource usage:

```python
app = TradingApp(service_id="risk-checker")
app.with_signals(False).with_data(False)
# Only app.positions, app.balance, app.orders are available
```

## Unit tests — required for all public APIs

Every public symbol MUST have unit tests.  The SDK is the **wire protocol
authority** — if its models or headers are wrong, every downstream service
(simple-strategy, ingestion, risk, executor) breaks silently.

### What must be tested

| Layer             | What to test                                 | Example                                                                                |
|-------------------|----------------------------------------------|----------------------------------------------------------------------------------------|
| **Models**        | Round-trip JSON serialization                | `Bar.model_validate_json(bar.model_dump_json()) == bar`                                |
| **Models**        | Field validation rejects bad data            | `Bar(symbol=123)` → raises `ValidationError`                                           |
| **Headers**       | `make_headers()` output is correct           | `make_headers(message_type="bar")` → contains `message_type`, `source_app`, `sequence` |
| **Headers**       | `parse_message()` deserializes correctly     | `parse_message(MessageType.DATA_READY, payload)` → `DataReady` instance                |
| **Headers**       | `build_event_key()` is deterministic         | Same inputs → same key string                                                          |
| **Configuration** | `TopicRegistry` names are environment-scoped | `TopicRegistry(env="dev").events.name == "dev-event"`                                  |
| **Configuration** | `ServiceSettings` loads from env vars        | `SDK_ENV=tst` → `settings.env == "tst"`                                                |

### How to write SDK unit tests

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

### Why unit tests are non-negotiable

The testing repo (`trading-cz/testing`) uses the SDK as a **tool** to:
- Build correct Kafka headers via `make_headers()`
- Serialize messages via `Bar.model_dump_json()`, `DataReady(...)`, etc.
- Validate received messages via `TradingSignal.model_validate_json(msg)`

If the SDK's wire format is broken, the testing repo **cannot detect it** — it
trusts the SDK.  The safety net is the SDK's own unit test suite, which must
pass on every PR.

**Rule**: No SDK PR merges without green CI (pytest + mypy + ruff).

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check tradingcz/
mypy tradingcz/
```

## See also

- **[docs/python314.md](docs/python314.md)** — modern Python 3.14 patterns used in this codebase
