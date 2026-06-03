# SDK Repository — Proposed Structure

> **Status**: Proposal · **Date**: 2026-06-02  
> **Principle**: Maximize discoverability, minimize ambiguity, make the right thing the easy thing.

---

## 1. Current Problems (Why Redesign)

| # | Problem | Impact |
|---|---------|--------|
| 1 | **`data.py` coexists with `data/` package** — `tradingcz/sdk/data.py` (legacy `DataClient`) and `tradingcz/sdk/data/` (new clients) create mypy import ambiguity | `from tradingcz.sdk.data import ...` is ambiguous; mypy fails |
| 2 | **Clients are scattered** — `data/`, `positions.py`, `balance.py`, `orders.py`, `signals.py` all at `sdk/` level with no grouping | User can't find clients; no single "clients" entry point |
| 3 | **`model/ingestion/` is misleading** — contains `Bar`, `Quote`, `Trade` used by *everyone*, not just ingestion | New users look in wrong place for market data models |
| 4 | **`sdk/` inside `tradingcz/` inside repo named `sdk/`** — `tradingcz.sdk.sdk.*` is confusing; what is the "SDK" part? | Namespace confusion; folder name doesn't describe contents |
| 5 | **Public vs private is inconsistent** — `_app.py`, `_service.py` are underscore-prefixed but are THE public API; `retry.py` is public but `_registry.py` is private | No clear boundary between stable API and internals |
| 6 | **`serialization/` and `transport/` float at top level** — they're infrastructure, not domain concepts | Flat top-level makes it hard to see what's core vs domain |
| 7 | **`config.py` and `errors.py` are orphans** — top-level files with no grouping | Where do new utilities go? |
| 8 | **`__init__.py` re-exports are inconsistent** — `tradingcz/__init__.py` documents the API but doesn't re-export; `tradingcz/sdk/__init__.py` does re-export | Users don't know where to import from |
| 9 | **`model/enum/` is singular** — inconsistent with `models/` (plural) | Minor but breaks naming consistency |
| 10 | **README doesn't show folder tree** — new users can't visualize the structure | Poor onboarding |

---

## 2. Proposed Structure

```
tradingcz/                         # Python package root
├── __init__.py                    # Top-level convenience re-exports
├── py.typed                       # PEP 561 marker
│
├── models/                        # 📦 Data models — the "what" of the system
│   ├── __init__.py                # Re-exports commonly used models
│   ├── market/                    # Market data DTOs
│   │   ├── __init__.py
│   │   ├── bar.py                 # Bar (OHLCV)
│   │   ├── quote.py               # Quote (bid/ask)
│   │   ├── trade.py               # Trade (tick)
│   │   ├── snapshot.py            # Snapshot (latest quote+trade+bars)
│   │   ├── stream_quote.py        # StreamQuote (real-time)
│   │   └── option_snapshot.py     # OptionSnapshot (greeks)
│   ├── events.py                  # DataRequest, DataReady, DataError, ServiceRequest
│   ├── headers.py                 # Header, MessageType, make_headers(), build_event_key(), parse_message()
│   ├── health.py                  # ServiceLifecycle
│   ├── signal.py                  # TradingSignal
│   ├── executor/                  # 🔒 FROZEN — do not modify
│   │   ├── __init__.py
│   │   ├── events/
│   │   │   ├── __init__.py
│   │   │   ├── base_event.py
│   │   │   ├── execution_request_event.py
│   │   │   ├── service_request_event.py
│   │   │   └── single_order_request.py
│   │   └── orders/
│   │       ├── __init__.py
│   │       ├── broker_order_response.py
│   │       └── single_market_orders/
│   │           ├── __init__.py
│   │           ├── market_order.py
│   │           ├── limit_order.py
│   │           ├── bracket_order.py
│   │           ├── stop_order.py
│   │           ├── trailing_stop_order.py
│   │           ├── oco_order.py
│   │           └── oto_order.py
│   └── enums/                     # Enumerations
│       ├── __init__.py
│       ├── adjustment.py          # Adjustment (RAW, SPLIT, DIVIDEND, ALL)
│       ├── order.py               # OrderSide, OrderType, OrderClass, OrderStatus, TimeInForce
│       ├── timeframe.py           # Timeframe (M1..MN1)
│       └── event.py               # Event-type enums
│
├── clients/                       # 🔌 Client API — the "how to interact" layer
│   ├── __init__.py                # Re-exports ALL public client classes
│   ├── base.py                    # BaseDataClient, StreamHandle[T]
│   ├── data/                      # Market data clients
│   │   ├── __init__.py
│   │   ├── stock.py               # StockDataClient  — bars(), quotes(), trades()
│   │   ├── options.py             # OptionsDataClient — snapshots(), chain()
│   │   └── corporate.py           # CorporateActionsClient — dividends(), splits()
│   ├── positions.py               # PositionClient — get_positions(), get_position()
│   ├── balance.py                 # BalanceClient — get_balance(), get_buying_power()
│   ├── orders.py                  # OrderClient — get_orders(), get_order_status()
│   └── signals.py                 # SignalPublisher — publish()
│
├── framework/                     # 🏗️ Application framework — extend to build services
│   ├── __init__.py                # Re-exports ServiceApp, TradingApp
│   ├── service.py                 # ServiceApp — base class for ALL services
│   ├── trading.py                 # TradingApp — strategy/consumer role
│   ├── health.py                  # HealthPublisher, HealthMonitor
│   └── helpers.py                 # FireAndForget, RequestReply
│
├── core/                          # ⚙️ Infrastructure — transport, messaging, serialization
│   ├── __init__.py
│   ├── transport/                 # Kafka primitives
│   │   ├── __init__.py            # Re-exports KafkaTransport, KafkaChannel
│   │   ├── kafka.py               # KafkaTransport, KafkaChannel
│   │   ├── message.py             # KafkaMessage
│   │   ├── hash_utils.py          # murmur2(), partition_for()
│   │   └── dedup.py               # DedupFilter
│   ├── messaging/                 # Typed messaging layer
│   │   ├── __init__.py            # Re-exports TypedProducer, TypedConsumer, TypedParser
│   │   ├── producer.py            # TypedProducer[T]
│   │   ├── consumer.py            # TypedConsumer[T], TypedParser
│   │   └── request_reply.py       # RequestReplyClient
│   ├── topics.py                  # TopicRegistry, TopicConfig
│   └── serialization/             # Codec infrastructure
│       ├── __init__.py            # Re-exports JsonCodec, Serializer, Deserializer, Codec
│       ├── protocol.py            # Serializer[T], Deserializer[T], Codec[T]
│       └── json_codec.py          # JsonCodec[T]
│
├── common/                        # 🧰 Shared utilities — no domain knowledge
│   ├── __init__.py
│   ├── config.py                  # KafkaSettings, LoggingSettings
│   ├── errors.py                  # SdkError hierarchy
│   ├── retry.py                   # Retry[T] — generic async retry
│   └── registry.py                # Registry[K, V] — generic class registry
│
└── indicators/                    # 📊 Technical analysis
    ├── __init__.py                # Re-exports calculate_atr
    └── atr.py                     # calculate_atr() — Wilder's ATR
```

---

## 3. Folder Purposes

### `models/` — Data Models
**What goes here**: Pydantic `BaseModel` classes. Frozen dataclass-style DTOs. Wire-format message types. Enums.

**What does NOT go here**: Any I/O. Any Kafka knowledge. Any business logic. Any computation beyond `@field_validator`.

**Rules**:
- Every model is a frozen Pydantic `BaseModel` (or `StrEnum`/`IntEnum` for enums)
- Models have NO dependencies on `clients/`, `framework/`, `core/`, or `common/`
- Models MAY reference each other (e.g., `Snapshot` contains `Quote`, `Trade`, `Bar`)
- New market data models go in `models/market/`
- `models/executor/` is **frozen** — no changes allowed

**Why `models/` not `model/`**: Plural matches the mental model ("I'm looking for models"). Consistent with `clients/`, `enums/`.

**Why `market/` not `ingestion/`**: `Bar`, `Quote`, `Trade` are used by strategies, executors, risk — not just ingestion. The old name was a historical accident.

---

### `clients/` — Client API
**What goes here**: High-level classes that perform actions: request data, get positions, publish signals. These are what 95% of users interact with.

**What does NOT go here**: Transport internals. Serialization details. Kafka topics. Health checks.

**Rules**:
- Every public class in `clients/` is a "Client" — something you call methods on
- Clients hide all transport/serialization complexity
- Clients accept typed domain models, return typed domain models
- `StreamHandle[T]` is the only transport-level concept that leaks through (async iteration is inherently transport-aware)
- New client types go directly in `clients/` (flat) or in a sub-package if they have multiple files
- `base.py` contains the shared base class — users may import it to build custom clients

**Naming convention**: `{Domain}Client` for data clients, `{Domain}Publisher` for fire-and-forget senders.

---

### `framework/` — Application Framework
**What goes here**: The base classes you extend to build a service (`ServiceApp`) or strategy (`TradingApp`). Lifecycle management. Health publishing. Internal messaging helpers.

**What does NOT go here**: Domain logic. Client implementations. Transport primitives.

**Rules**:
- All modules are open for extension — no underscore barriers
- `ServiceApp` and `TradingApp` are the primary entry points
- `health.py` provides `HealthPublisher` and `HealthMonitor` for custom health checks
- `helpers.py` provides `FireAndForget` and `RequestReply` for building custom messaging patterns
- Users may subclass or import any class in `framework/`

---

### `core/` — Infrastructure
**What goes here**: Kafka transport, typed messaging, serialization codecs, topic registry, deduplication. The plumbing.

**What does NOT go here**: Business logic. Domain models. Client classes.

**Rules**:
- `core/transport/` — raw Kafka: channels, producers, consumers, messages, partitioning
- `core/messaging/` — typed layer on top of transport: `TypedProducer[T]`, `TypedConsumer[T]`, `TypedParser`, `RequestReplyClient`
- `core/serialization/` — codec abstraction: `Serializer[T]`, `Deserializer[T]`, `Codec[T]`, `JsonCodec[T]`
- `core/topics.py` — topic naming and configuration
- All modules are importable directly — no underscore barriers

**Boundary**: `core/` has NO knowledge of trading concepts (signals, bars, orders). It only knows about bytes, topics, and generic types.

---

### `common/` — Shared Utilities
**What goes here**: Configuration, error hierarchy, retry logic, generic registry. Pure utilities with zero domain knowledge.

**What does NOT go here**: Anything that knows about trading, Kafka topics, market data, or signals.

**Rules**:
- `common/` could be extracted into a separate `tradingcz-common` package
- No imports from `models/`, `clients/`, `framework/`, `core/`
- `registry.py` is open for use — generic class registry pattern

---

### `indicators/` — Technical Analysis
**What goes here**: Pure functions that compute technical indicators from market data.

**Rules**:
- Functions take `list[Bar]` (or similar) and return numbers
- No side effects, no I/O, no state
- Each indicator gets its own file
- Re-exported from `tradingcz.indicators`

---

## 4. Public API Surface

### Primary Entry Points (import from `tradingcz`)

```python
# ── Application classes ──────────────────────────
from tradingcz import TradingApp, ServiceApp

# ── Data models ──────────────────────────────────
from tradingcz import Bar, Quote, Trade, Snapshot, OptionSnapshot, StreamQuote
from tradingcz import DataRequest, DataReady, DataError
from tradingcz import TradingSignal, ServiceLifecycle
from tradingcz import MessageType, Header, make_headers, build_event_key

# ── Clients (also available via app.stock, app.signals, etc.) ─
from tradingcz import (
    StockDataClient,
    OptionsDataClient,
    CorporateActionsClient,
    PositionClient,
    BalanceClient,
    OrderClient,
    SignalPublisher,
)

# ── Configuration ────────────────────────────────
from tradingcz import KafkaSettings, LoggingSettings

# ── Errors ───────────────────────────────────────
from tradingcz import SdkError, TransportError, ConfigurationError

# ── Indicators ───────────────────────────────────
from tradingcz import calculate_atr

# ── Utilities ────────────────────────────────────
from tradingcz import Retry
```

### Secondary Entry Points (for advanced use)

```python
# ── Transport (building custom channels) ─────────
from tradingcz.core.transport import KafkaTransport, KafkaChannel, KafkaMessage

# ── Typed messaging ──────────────────────────────
from tradingcz.core.messaging import TypedProducer, TypedConsumer, TypedParser

# ── Serialization ────────────────────────────────
from tradingcz.core.serialization import JsonCodec, Serializer, Deserializer, Codec

# ── Topics ───────────────────────────────────────
from tradingcz.core.topics import TopicRegistry, TopicConfig

# ── Request/Reply ────────────────────────────────
from tradingcz.core.messaging import RequestReplyClient

# ── Health (building custom monitors) ────────────
from tradingcz.framework import HealthPublisher, HealthMonitor

# ── Full model tree ──────────────────────────────
from tradingcz.models.market import Bar, Quote, Trade, Snapshot
from tradingcz.models.enums import Timeframe, OrderSide, OrderStatus
```

### All Modules Are Open for Extension

The SDK is in active development (pre-1.0). No module is closed off with `_` prefix barriers.
Every file, class, and function is importable and subclassable. The `__init__.py`
re-exports define the **recommended** API surface, but power users can reach into
any module to extend or customize behavior.

**Example — building a custom serializer**:
```python
from tradingcz.core.serialization.protocol import Serializer

class AvroSerializer(Serializer[MyModel]):
    def serialize(self, value: MyModel) -> bytes: ...
    def content_type(self) -> str: return "application/avro"
```

**Example — extending the base data client**:
```python
from tradingcz.clients.base import BaseDataClient

class CustomDataClient(BaseDataClient):
    async def my_custom_query(self, symbols: list[str]) -> dict[str, list[Bar]]:
        ...
```

When the SDK stabilizes (v1.0), we may introduce a `_private` subpackage
for implementation details that should not be relied upon. Until then,
everything is open.

---

## 5. Import Path Changes (from current → proposed)

| Current Import | Proposed Import | Notes |
|---|---|---|
| `tradingcz.sdk._app.TradingApp` | `tradingcz.TradingApp` | Top-level convenience |
| `tradingcz.sdk._service.ServiceApp` | `tradingcz.ServiceApp` | Top-level convenience |
| `tradingcz.sdk.data._stock.StockDataClient` | `tradingcz.clients.data.stock.StockDataClient` | Or `tradingcz.StockDataClient` |
| `tradingcz.sdk.data.DataClient` | **REMOVED** | Legacy monolithic client; use per-asset clients |
| `tradingcz.sdk.signals.SignalPublisher` | `tradingcz.clients.signals.SignalPublisher` | |
| `tradingcz.sdk.positions.PositionClient` | `tradingcz.clients.positions.PositionClient` | |
| `tradingcz.sdk.balance.BalanceClient` | `tradingcz.clients.balance.BalanceClient` | |
| `tradingcz.sdk.orders.OrderClient` | `tradingcz.clients.orders.OrderClient` | |
| `tradingcz.sdk._health.HealthPublisher` | `tradingcz.framework.health.HealthPublisher` | Open for extension |
| `tradingcz.sdk._health.HealthMonitor` | `tradingcz.framework.health.HealthMonitor` | Open for extension |
| `tradingcz.sdk._helpers._FireAndForget` | `tradingcz.framework.helpers.FireAndForget` | Open for extension |
| `tradingcz.sdk._helpers._RequestReply` | `tradingcz.framework.helpers.RequestReply` | Open for extension |
| `tradingcz.sdk.data._base._BaseDataClient` | `tradingcz.clients.base.BaseDataClient` | Open for subclassing |
| `tradingcz.sdk.retry.Retry` | `tradingcz.Retry` | Top-level convenience |
| `tradingcz.model.ingestion.Bar` | `tradingcz.models.market.Bar` | Also `tradingcz.Bar` |
| `tradingcz.model.ingestion.Quote` | `tradingcz.models.market.Quote` | Also `tradingcz.Quote` |
| `tradingcz.model.events.DataRequest` | `tradingcz.models.events.DataRequest` | Also `tradingcz.DataRequest` |
| `tradingcz.model.headers.MessageType` | `tradingcz.models.headers.MessageType` | Also `tradingcz.MessageType` |
| `tradingcz.model.enum.timeframe.Timeframe` | `tradingcz.models.enums.Timeframe` | |
| `tradingcz.config.KafkaSettings` | `tradingcz.common.config.KafkaSettings` | Also `tradingcz.KafkaSettings` |
| `tradingcz.errors.SdkError` | `tradingcz.common.errors.SdkError` | Also `tradingcz.SdkError` |
| `tradingcz.transport.channel.KafkaTransport` | `tradingcz.core.transport.kafka.KafkaTransport` | |
| `tradingcz.transport.channel.KafkaChannel` | `tradingcz.core.transport.kafka.KafkaChannel` | |
| `tradingcz.transport.kafka_message.KafkaMessage` | `tradingcz.core.transport.message.KafkaMessage` | |
| `tradingcz.transport.hash.murmur2` | `tradingcz.core.transport.hash_utils.murmur2` | |
| `tradingcz.transport._dedup.DedupFilter` | `tradingcz.core.transport.dedup.DedupFilter` | |
| `tradingcz.transport.stream.TypedProducer` | `tradingcz.core.messaging.producer.TypedProducer` | |
| `tradingcz.transport.stream.TypedConsumer` | `tradingcz.core.messaging.consumer.TypedConsumer` | |
| `tradingcz.transport.stream.TypedParser` | `tradingcz.core.messaging.consumer.TypedParser` | |
| `tradingcz.transport.request_reply.RequestReplyClient` | `tradingcz.core.messaging.request_reply.RequestReplyClient` | |
| `tradingcz.transport.topics.TopicRegistry` | `tradingcz.core.topics.TopicRegistry` | |
| `tradingcz.serialization.protocol.Serializer` | `tradingcz.core.serialization.protocol.Serializer` | |
| `tradingcz.serialization.json_codec.JsonCodec` | `tradingcz.core.serialization.json_codec.JsonCodec` | Or `tradingcz.JsonCodec` |
| `tradingcz.indicators.atr.calculate_atr` | `tradingcz.indicators.calculate_atr` | Same, just re-exported |

---

## 6. Naming Conventions

### Folder Names
| Convention | Example | Rationale |
|---|---|---|
| **Plural** for collections | `models/`, `clients/`, `enums/` | "I need a model" → look in `models/` |
| **Singular** for singleton concepts | `core/`, `framework/`, `common/` | There's only one framework |
| **Domain name** for sub-packages | `market/`, `data/`, `transport/` | Describes what's inside |
| **No vendor names** | ❌ `alpaca/` in SDK | SDK is provider-agnostic |

### File Names
| Convention | Example | Rationale |
|---|---|---|

| **`snake_case`** for all files | `stream_quote.py`, `option_snapshot.py` | Python convention |
| **One class per file** (for models) | `bar.py` → `Bar` | Easy to find; no scrolling |
| **Grouped by concern** (for clients) | `stock.py` → `StockDataClient` | Related methods together |
| **No `_` prefix** on any file | `service.py` not `_service.py` | Library is open for extension |

### Class Names
| Convention | Example | Rationale |
|---|---|---|
| **`{Domain}Client`** for data clients | `StockDataClient`, `OptionsDataClient` | Clearly a client; clearly what data |
| **`{Domain}Client`** for service clients | `PositionClient`, `BalanceClient`, `OrderClient` | Consistent with data clients |
| **`{Domain}Publisher`** for fire-and-forget | `SignalPublisher` | Different from request/response clients |
| **`{Concept}App`** for application classes | `TradingApp`, `ServiceApp` | These are the entry points |
| **`{Concept}{Thing}`** for models | `DataRequest`, `TradingSignal`, `ServiceLifecycle` | Descriptive; no suffix needed |

### Public vs Internal
| Visibility | Markers | Example |
|---|---|---|
| **Recommended API** | Re-exported in `__init__.py` | `from tradingcz import TradingApp, Bar` |
| **Stable module** | Direct import; documented | `from tradingcz.clients.signals import SignalPublisher` |
| **Extension point** | Direct import; subclassable | `from tradingcz.clients.base import BaseDataClient` |
| **Internal detail** | No special marker; may change | `from tradingcz.core.transport.dedup import DedupFilter` |

> **Note**: In early development (pre-1.0), ALL modules are open. The `__init__.py`
> re-exports signal what we consider the **recommended** API, but nothing is
> hidden. When the library stabilizes, we may introduce a `_private` subpackage
> for implementation details that should not be relied upon.

---

## 7. Developer Experience

### Quick-Start: The 3-Minute Tour

```python
# 1. EVERYTHING you commonly need is at the top level
from tradingcz import TradingApp, Bar, TradingSignal, calculate_atr

# 2. Build a strategy in 3 steps
async with TradingApp(service_id="my-strategy") as app:
    # Step A: Get historical data
    bars = await app.stock.bars(["AAPL", "MSFT"], days=30)

    # Step B: Compute indicators
    for symbol, history in bars.items():
        atr = calculate_atr(history, period=14)

    # Step C: Stream real-time data
    async with app.stock.quotes(["AAPL"]) as stream:
        async for quote in stream:
            if quote.quote.bid_price > threshold:
                signal = TradingSignal(
                    symbol="AAPL",
                    side="LONG",
                    entry_price=quote.quote.ask_price,
                    strategy_id="my-strategy",
                )
                await app.signals.publish(signal)
```

### Where to Find Things (Mental Model)

```
"I need a data structure"          → tradingcz.models
"I need to request data"           → tradingcz.clients
"I need to build a service"        → tradingcz.framework
"I need to understand the wire"    → tradingcz.core
"I need a utility function"        → tradingcz.common
"I need an indicator"              → tradingcz.indicators
"I just want to get started"       → from tradingcz import TradingApp
```

### Discovery Patterns

| If you want to... | Import from | Look for class/function named... |
|---|---|---|
| Get historical bars | `tradingcz.clients.data.stock` | `StockDataClient` |
| Stream real-time quotes | `tradingcz.clients.data.stock` | `StockDataClient.quotes()` |
| Get current positions | `tradingcz.clients.positions` | `PositionClient` |
| Publish a trading signal | `tradingcz.clients.signals` | `SignalPublisher` |
| Build a custom service | `tradingcz.framework` | `ServiceApp` |
| Understand a message type | `tradingcz.models.headers` | `MessageType` enum |
| Serialize/deserialize | `tradingcz.core.serialization` | `JsonCodec` |
| Work with Kafka directly | `tradingcz.core.transport` | `KafkaTransport`, `KafkaChannel` |

---

## 8. SDK Philosophy

### The SDK is the Source of Truth

Every service in the trading-cz platform shares these concepts:
- **Data models** — what a Bar, Quote, Trade, Signal, or Order looks like on the wire
- **Wire protocol** — how messages are enveloped, routed, correlated, and versioned
- **Transport** — how bytes move between services (Kafka topics, partitions, serialization)
- **Client patterns** — how to request data, stream data, publish signals, query state

The SDK owns ALL of these. No other repository defines its own message format, its own serialization, or its own Kafka topic naming. If two services disagree on the wire format, the SDK is the arbiter.

### Design Principles

1. **The top-level is for beginners.** `from tradingcz import TradingApp, Bar` should cover 80% of use cases. Power users drill into sub-packages.

2. **Folders describe their contents.** You should never open a folder and be surprised by what's inside. `models/` has models. `clients/` has clients. `core/transport/` has transport.

3. **Public API is intentional.** If a class is re-exported in an `__init__.py`, it's supported. If you have to import from a `_`-prefixed module, you're off the map.

4. **No circular dependencies.** The dependency graph is a DAG:
   ```
   common/  ←  models/  ←  core/  ←  clients/  ←  framework/
     ↑           ↑          ↑
   indicators/   └──────────┘
   ```
   - `common/` depends on nothing (pure Python + pydantic)
   - `models/` depends on `common/` (for config types in models? actually no — models should be pure)
   - `core/` depends on `common/` + `models/`
   - `clients/` depends on `core/` + `models/`
   - `framework/` depends on `clients/` + `core/` + `models/`
   - `indicators/` depends on `models/` (takes `Bar` as input)

5. **One obvious way to do it.** There should be one clear import path for each concept. If users are importing the same class from 3 different paths, the structure is wrong.

6. **Open for extension.** No module uses `_` prefix barriers. The library is pre-1.0 and in active development — consumers should be able to import, subclass, and extend any class. The `__init__.py` re-exports define the **recommended** API; direct module imports are for power users who accept the risk of change.

---

## 9. Files to Delete (Cleanup)

These files are part of the current structure and should be **removed**:

| File | Reason |
|---|---|
| `tradingcz/sdk/data.py` | Legacy monolithic `DataClient`; replaced by `clients/data/stock.py` etc. |
| `tradingcz/sdk/_registry.py` | Moved to `common/registry.py` |
| `tradingcz/sdk/retry.py` | Moved to `common/retry.py` |
| `tradingcz/sdk/` (entire folder) | Dissolved into `clients/` + `framework/` + `common/` |
| `tradingcz/transport/` (entire folder) | Moved to `core/transport/` |
| `tradingcz/serialization/` (entire folder) | Moved to `core/serialization/` |
| `tradingcz/config.py` | Moved to `common/config.py` |
| `tradingcz/errors.py` | Moved to `common/errors.py` |
| `tradingcz/model/` (entire folder) | Renamed to `models/` |

---

## 10. Migration Notes

### For `ingestion` consumers

The ingestion repository imports heavily from the SDK. Key changes:

```python
# BEFORE                                  # AFTER
from tradingcz.sdk._service import ServiceApp     → from tradingcz import ServiceApp
from tradingcz.sdk._health import HealthMonitor   → from tradingcz.framework import HealthMonitor
from tradingcz.model.events import DataRequest    → from tradingcz.models.events import DataRequest
from tradingcz.model.ingestion import Bar         → from tradingcz.models.market import Bar
from tradingcz.transport import KafkaTransport    → from tradingcz.core.transport import KafkaTransport
from tradingcz.serialization import JsonCodec     → from tradingcz.core.serialization import JsonCodec
from tradingcz.config import KafkaSettings        → from tradingcz.common.config import KafkaSettings
```

### For `simple-strategy` consumers

```python
# BEFORE                                  # AFTER
from tradingcz.sdk import TradingApp              → from tradingcz import TradingApp
from tradingcz.sdk._health import HealthPublisher → from tradingcz.framework import HealthPublisher
from tradingcz.sdk.signals import SignalPublisher → from tradingcz.clients.signals import SignalPublisher
from tradingcz.sdk._helpers import _FireAndForget → from tradingcz.framework.helpers import FireAndForget
from tradingcz.model.ingestion import Bar         → from tradingcz.models.market import Bar
from tradingcz.model.signal import TradingSignal  → from tradingcz.models.signal import TradingSignal
from tradingcz.transport import KafkaTransport    → from tradingcz.core.transport import KafkaTransport
from tradingcz.serialization import JsonCodec     → from tradingcz.core.serialization import JsonCodec
from tradingcz.indicators import calculate_atr    → from tradingcz import calculate_atr  # unchanged
```

### Migration Strategy

1. **Phase 1**: Create new folder structure alongside old one. Both coexist.
2. **Phase 2**: Add deprecation warnings to old import paths (using `__getattr__` at module level).
3. **Phase 3**: Migrate `ingestion` and `simple-strategy` to new import paths.
4. **Phase 4**: Remove old folders and files.

Since backward compatibility is not required, phases 2-3 can be done in a single PR per consumer.

---

## 11. README Template

The new `README.md` should follow this structure:

### Title + Badge
```
# trading-sdk
Shared SDK and data models for the trading-cz platform
```

### Folder Tree (ASCII)
Show the top 3 levels of the structure above.

### Quick Start
```python
from tradingcz import TradingApp, Bar, TradingSignal

async with TradingApp(service_id="my-strategy") as app:
    bars = await app.stock.bars(["AAPL"], days=30)
    async with app.stock.quotes(["AAPL"]) as stream:
        async for quote in stream:
            ...
```

### Common Tasks (cookbook style)
- How to get historical bars
- How to stream real-time quotes
- How to publish a trading signal
- How to query positions
- How to build a custom service

### Package Organization
Brief description of each top-level folder and when to use it.

### API Reference
Link to the key modules (or auto-generated docs).

### Development
How to run tests, lint, type-check.
