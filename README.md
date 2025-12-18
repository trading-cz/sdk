# Trading SDK (`trading-sdk`)

Shared SDK and data models for the trading platform.

## Overview

- **Package name**: `trading-sdk`
- **Namespace**: `tradingcz.model` (shared namespace pattern)
- **Purpose**: Provide shared data models, enums, DTOs, and utilities for trading services
- **Hand-written code**: Enums, DTOs, utilities - manually maintained
- **GitHub Releases**: Installable wheel via direct URL

---

## Installation

```bash
# Install from GitHub Releases (wheel URL)
pip install https://github.com/trading-cz/sdk/releases/download/v0.0.8/trading_sdk-0.0.8-py3-none-any.whl
```

This creates the `tradingcz.model` namespace, which composes cleanly with other `tradingcz.*` packages (e.g., `tradingcz.ingestion` from ingestion-alpaca).

---

## Project Structure

```
sdk/
├── pyproject.toml                    # Package config (version, namespace setup)
├── README.md
│
├── tradingcz/                        # Namespace package root
│   ├── __init__.py                   # Uses pkgutil.extend_path() for composition
│   └── model/                        # Core models (tradingcz.model.*)
│       ├── __init__.py               # Re-exports enums + DTOs
│       ├── domain/                   # Data domain models
│       │   ├── bar.py                # OHLCV bar
│       │   ├── quote.py              # Bid/ask quote
│       │   ├── trade.py              # Individual trade
│   Namespace Pattern

This package uses the **namespace package pattern** (PEP 420 via `pkgutil.extend_path()`):

- **Distribution name**: `trading-sdk`
- **Import namespace**: `tradingcz.model` (shared top-level `tradingcz`)
- **Composition**: Works seamlessly with other `tradingcz.*` packages across repos
  - `tradingcz.model` ← from `trading-sdk`
  - `tradingcz.ingestion` ← from `ingestion-alpaca`
  - `tradingcz.common` ← from `ingestion-alpaca`

Install both wheels, and Python's import system will find all subpackages without conflicts.
```

### Folder Responsibilities

| Folder | Type | Purpose | Who Edits |
|--------|------|---------|-----------|
| `schemas/` | Source | Avro schemas (Kafka contracts) | Developers |
| `src/.../enums/` | Source | Hand-written enumerations | Developers |
| `src/.../dto/` | Source | Hand-written DTOs | Developers |
| `src/.../utils/` | Source | Hand-written utilities | Developers |
| `src/.../kafka/` | Generated | Auto-generated from Avro | **GitHub Actions only** |

---

## Package Structure After Install

```python
from tradingcz.model import (
    # Enums (hand-written)
    Timeframe, Adjustment, SortOrder, OrderSide, OrderType,
    
    # DTOs (hand-written)
    Bar, Quote, Trade, Snapshot,
    
    # Converters (hand-written)
    quote_to_kafka, trade_to_kafka,
)
```

---

## GitHub Actions

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | Push / PR | Linting, type checking, testing |
| `build-and-push.yml` | Tag `v*.*.*` | Builds package → publishes to GitHub Packages |

---

## Developer Workflows

### Adding a New Enum (hand-written)

1. Create file in `tradingcz/model/enums/`:

```python
# tradingcz/model/enums/order.py
from enum import Enum

class OrderSide(str, Enum):
    """Order side for trading."""
    BUY = "buy"
    SELL = "sell"

class OrderType(str, Enum):
    """Order type."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
```

2. Export in `tradingcz/model/enums/__init__.py`:

```python
from .order import OrderSide, OrderType
from .timeframe import Timeframe
from .adjustment import Adjustment
```

3. Commit and push - CI will validate code quality

### Adding a New DTO (hand-written)

1. Create file in `tradingcz/model/dto/`:

```python
# tradingcz/model/dto/bar.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass(slots=True)
class Bar:
    """OHLCV bar for charting and backtesting."""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: Optional[int] = None
    vwap: Optional[float] = None
```

2. Export in `tradingcz/model/dto/__init__.py`

### Adding a Converter (hand-written)

```python
# tradingcz/model/utils/converters.py
from tradingcz.model.domain import Quote


def quote_to_kafka(quote: Quote) -> dict:
    """Convert REST DTO to Kafka payload."""
    return {
        "symbol": quote.symbol,
        "timestamp": int(quote.timestamp.timestamp() * 1_000_000),  # micros
        "bid_price": quote.bid_price,
        "ask_price": quote.ask_price,
        "bid_size": quote.bid_size or 0,
        "ask_size": quote.ask_size or 0,
    }
```

---

## Installation

```bash
# Install from GitHub Releases
pip install https://github.com/trading-cz/sdk/releases/download/v0.0.7/trading_sdk-0.0.7-py3-none-any.whl

# Or install from git
pip install git+https://github.com/trading-cz/sdk.git@main
```

**⚠️ Upgrading:**
```bash
pip uninstall trading-sdk -y
pip install <new-version> --no-cache-dir
```

---

## Available Models

### Enums (hand-written)

| Enum | Values | Purpose |
|------|--------|---------|
| `Timeframe` | 1Min, 5Min, 15Min, 1Hour, 1Day | Bar aggregation periods |
| `Adjustment` | raw, split, dividend, all | Corporate action adjustments |
| `SortOrder` | asc, desc | Time-series ordering |
| `OrderSide` | buy, sell | Trade direction |
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
