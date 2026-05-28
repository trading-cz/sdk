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

| Variable | Default | Description |
|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker addresses |
| `KAFKA_CONSUMER_GROUP` | `<service_id>` | Consumer group id |
| `SDK_ENV` | `dev` | Deployment environment |
| `SDK_HEALTH_INTERVAL` | `300` | Heartbeat interval (seconds) |
| `SDK_BROKER` | `alpaca` | Broker identifier (TradingApp only) |

## Feature flags

Disable clients you don't need to reduce resource usage:

```python
app = TradingApp(service_id="risk-checker")
app.with_signals(False).with_data(False)
# Only app.positions, app.balance, app.orders are available
```

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check tradingcz/
mypy tradingcz/
```

## See also

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — module map, design decisions, transport layer details
- **[docs/python314.md](docs/python314.md)** — modern Python 3.14 patterns used in this codebase
