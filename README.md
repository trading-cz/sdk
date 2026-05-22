# Trading SDK (`trading-sdk`)

Shared SDK, data models, transport abstractions, and utilities for the trading platform.

## Overview

- **Package name**: `trading-sdk`
- **Namespace**: `tradingcz` (shared across all trading services)
- **Purpose**: Eliminate code duplication across ingestion, strategy, risk, and executor services
- **Editable install**: `pip install -e /path/to/sdk` in each service's virtual environment

---

## Installation

```bash
# Editable install (development)
pip install -e /path/to/sdk

# With optional aiokafka support (for strategy pods)
pip install -e "/path/to/sdk[kafka-aio]"
```

---

## Project Structure

```
sdk/
├── pyproject.toml
├── README.md
│
├── tradingcz/
│   ├── __init__.py              # Namespace package (pkgutil.extend_path)
│   ├── py.typed                 # PEP 561 marker
│   │
│   ├── config/
│   │   ├── __init__.py          # Exports: KafkaSettings, ServerSettings, LoggingSettings
│   │   └── settings.py          # Pydantic BaseSettings classes
│   │
│   ├── model/
│   │   ├── __init__.py          # Re-exports all shared models
│   │   ├── enum/                # Timeframe, Adjustment, OrderSide, etc.
│   │   ├── ingestion/           # Bar, Quote, Trade, Snapshot (market data)
│   │   ├── events.py            # DataRequest, DataReady, DataError, parse_event
│   │   ├── signal.py            # TradingSignal, build_signal
│   │   ├── event_bus.py         # EventBus (JSON send/listen over Channel)
│   │   ├── kafka_key.py         # KafkaKey helper
│   │   └── encoder/             # JSON serialization mixins
│   │
│   ├── transport/
│   │   ├── __init__.py          # Exports: Channel, Message, Transport, KafkaChannel, KafkaTransport
│   │   ├── protocol.py          # Abstract channel/transport interfaces
│   │   └── kafka.py             # Confluent-kafka implementation
│   │
│   ├── receiver/
│   │   ├── __init__.py          # Exports: AioKafkaReceiverTransport
│   │   └── kafka_aio.py         # Async Kafka request/response transport (aiokafka)
│   │
│   ├── indicators/
│   │   ├── __init__.py          # Exports: calculate_atr
│   │   └── atr.py               # ATR indicator (Wilder method)
│   │
│   ├── io/                      # Reader/Writer ABCs (legacy)
│   ├── lang/                    # Version/utility helpers
│   └── logging/                 # setup_logging utility
```

---

## Usage

```python
from tradingcz.model import Bar, Quote, TradingSignal, DataRequest, DataReady
from tradingcz.config import KafkaSettings
from tradingcz.transport import KafkaTransport
from tradingcz.receiver import AioKafkaReceiverTransport
from tradingcz.indicators import calculate_atr
```
| `OrderType` | market, limit, stop, stop_limit | Order execution type |

### DTOs (hand-written)

| DTO | Fields | Purpose |
|-----|--------|---------|
| `Bar` | symbol, timestamp, OHLCV, vwap | Candlestick data |
| `Quote` | symbol, timestamp, bid/ask price+size | Level 1 quotes |
| `Trade` | symbol, timestamp, price, size | Individual trades |
| `Snapshot` | latest_trade, latest_quote, bars | Complete market state |

---

## Local Development

```bash
# Install in editable mode
pip install -e .

# Run tests
pytest tests/ -v

# Validate code quality (same checks as CI)
ruff check tradingcz/          # Fast linting (flake8 + isort checks)
pylint tradingcz/ --disable=import-error  # Comprehensive analysis
mypy tradingcz/                # Type checking

# Auto-fix issues
ruff check tradingcz/ --fix    # Auto-fix ruff issues
ruff format tradingcz/         # Format code
```

**Note**: Both `ruff` and `pylint` are configured in `pyproject.toml` and run in CI via MegaLinter. Local dev should verify both pass before pushing.

---

## Design Principles

1. **Simplicity** — Shared data models without code generation complexity
2. **Type safety** — All models use Pydantic or dataclasses
3. **Consistent naming** — `tradingcz.model.*` namespace everywhere
4. **Easy consumption** — One import for all models
5. **Maintainability** — All code is hand-written and version-controlled
