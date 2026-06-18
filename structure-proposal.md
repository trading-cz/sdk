# SDK Structure Proposal — Layered Domain-Driven

**Date:** 2026-06-18
**Branch:** `fix/event-models-event-type`
**Principle:** App classes at root. Domain packages for public API. `_`-prefixed directories hide transport/messaging/serialization machinery. No `util`, `common`, `core`, or `trading` (misleading — repo root is already `tradingcz`).

---

## Layer Model

```
┌──────────────────────────────────────────────┐
│ LAYER 4 — App Classes  (root .py files)       │
│ service_app.py    trading_app.py              │  ← starting point
├──────────────────────────────────────────────┤
│ LAYER 3 — Domain Packages  (public, stable)   │
│ market_data/  account/  health/               │
│ indicators/   patterns/                       │
├──────────────────────────────────────────────┤
│ LAYER 2 — Messaging  (_messaging/)            │
│ typed producer/consumer, fire&forget,         │  ← hidden
│ request/reply, event router, recovery         │
├──────────────────────────────────────────────┤
│ LAYER 1 — Transport  (_transport/)            │
│ Kafka channel, transport, topics, dedup       │  ← hidden
└──────────────────────────────────────────────┘

Layer dependency: higher → lower.  Never upward.
```

---

## Future Tree

```
tradingcz/sdk/
│
│  ═══════════════════════════════════════════════════════════
│  LAYER 4 — PUBLIC APP CLASSES  (your starting point)
│  ═══════════════════════════════════════════════════════════
│
├── __init__.py                   # from tradingcz.sdk import TradingApp, ServiceApp
├── service_app.py                # ServiceApp — base for ALL services
├── trading_app.py                # TradingApp — strategy/consumer batteries-included
│
│  ═══════════════════════════════════════════════════════════
│  LAYER 4b — CROSS-CUTTING  (public, small, root-level)
│  ═══════════════════════════════════════════════════════════
│
├── exceptions.py                 # SdkError → TransportError, SerializationError, ...
├── logging.py                    # setup_logging(), LokiJSONFormatter, LoggingSettings
│
│  ═══════════════════════════════════════════════════════════
│  LAYER 3 — PUBLIC DOMAIN PACKAGES  (what apps call)
│  ═══════════════════════════════════════════════════════════
│
├── market_data/                  # Historical + streaming market data + market clock
│   ├── __init__.py               #   StockDataClient, OptionsDataClient, CorporateActionsClient,
│   │                             #   TimeKeeper, MarketClockProvider
│   ├── _base.py                  #   BaseDataClient, StreamHandle  (internal to package)
│   ├── stock.py                  #   StockDataClient  (.bars, .stream_quotes, .stream_trades)
│   ├── options.py                #   OptionsDataClient  (.snapshots)
│   ├── corporate.py              #   CorporateActionsClient  (.dividends, .splits)
│   └── clock.py                  #   TimeKeeper  (.start_timekeeping, .get_warning_event)
│                                 #   MarketClockProvider  (Protocol)
│
├── account/                      # Account state + signal publishing
│   ├── __init__.py               #   BalanceClient, OrderClient, PositionClient,
│   │                             #   SignalPublisher
│   ├── balance.py                #   BalanceClient  (.get_balance, .get_buying_power)
│   ├── orders.py                 #   OrderClient    (.get_orders, .get_order_status)
│   ├── positions.py              #   PositionClient (.get_positions)
│   └── signals.py                #   SignalPublisher  (.publish)
│
├── health/                       # Service health monitoring
│   ├── __init__.py               #   HealthMonitor
│   └── monitor.py                #   HealthMonitor  (.on_down, .run)
│
├── indicators/                   # Technical indicators (pure functions, no I/O)
│   ├── __init__.py               #   calculate_atr
│   └── atr.py                    #   calculate_atr(bars, period) → float
│
├── patterns/                     # Reusable design patterns (public, stable)
│   ├── __init__.py               #   Registry, Retry
│   ├── registry.py               #   Registry — decorator-based class registry
│   └── retry.py                  #   Retry — async retry wrapper
│
│  ═══════════════════════════════════════════════════════════
│  MODELS — unchanged per constraint
│  ═══════════════════════════════════════════════════════════
│
├── models/
│   ├── __init__.py
│   ├── dispatch.py               #   model_for(), parse_message()
│   ├── headers.py                #   Header, EventHeaders, DataHeaders, KafkaKey
│   ├── enums/
│   │   ├── __init__.py
│   │   ├── event.py              #   EventType, EventStatus, StrategyType, Broker,
│   │   │                         #   AssetType, DataRequestType, MarketDataType,
│   │   │                         #   LifecycleEventType, ServiceRequestType, OrderRequest
│   │   ├── order.py              #   OrderSide, OrderType, OrderClass, OrderStatus,
│   │   │                         #   TimeInForce, SortOrder, TERMINAL_STATUSES
│   │   ├── timeframe.py          #   Timeframe
│   │   └── adjustment.py         #   Adjustment
│   ├── events/
│   │   ├── __init__.py
│   │   ├── data_request.py       #   DataRequest, DataReady, DataError
│   │   ├── execution_request.py  #   ExecutionRequestEvent
│   │   ├── lifecycle.py          #   LifecycleEvent
│   │   └── service_request.py    #   ServiceRequestEvent
│   ├── market/
│   │   ├── __init__.py           #   MarketItem, market_item_message_type
│   │   ├── bar.py                #   Bar
│   │   ├── quote.py              #   Quote
│   │   ├── trade.py              #   Trade
│   │   ├── stream_quote.py       #   StreamQuote
│   │   ├── snapshot.py           #   Snapshot
│   │   └── option_snapshot.py    #   OptionSnapshot
│   └── orders/
│       ├── __init__.py
│       ├── bracket_order.py      #   BracketOrderRequest
│       ├── limit_order.py        #   LimitOrderRequest
│       ├── market_order.py       #   MarketOrderRequest
│       ├── oco_order.py          #   OcoOrderRequest
│       ├── oto_order.py          #   OtoOrderRequest
│       ├── stop_order.py         #   StopOrderRequest
│       └── trailing_stop_order.py#   TrailingStopOrderRequest
│
│  ═══════════════════════════════════════════════════════════
│  LAYER 2 — HIDDEN: Messaging Patterns
│  ═══════════════════════════════════════════════════════════
│
├── _messaging/
│   ├── __init__.py
│   ├── typed.py                  #   TypedProducer, TypedConsumer, TypedParser
│   ├── fire_and_forget.py        #   FireAndForget
│   ├── request_reply.py          #   RequestReply, RequestReplyClient
│   ├── router.py                 #   EventRouter
│   ├── recovery.py               #   RecoveryReader
│   └── health_publisher.py       #   HealthPublisher  (used by ServiceApp internally)
│
│  ═══════════════════════════════════════════════════════════
│  LAYER 1 — HIDDEN: Low-Level Transport
│  ═══════════════════════════════════════════════════════════
│
├── _transport/
│   ├── __init__.py
│   ├── channel.py                #   KafkaChannel
│   ├── transport.py              #   KafkaTransport
│   ├── message.py                #   KafkaMessage
│   ├── topics.py                 #   TopicRegistry, TopicConfig
│   ├── dedup.py                  #   DedupFilter
│   └── settings.py               #   KafkaSettings
│
│  ═══════════════════════════════════════════════════════════
│  HIDDEN: Serialization
│  ═══════════════════════════════════════════════════════════
│
└── _serialization/
    ├── __init__.py
    ├── protocol.py               #   Serializer, Deserializer, Codec
    └── json.py                   #   JsonCodec, JsonSerializer
```

---

## What Each Kind of App Imports

### Strategy developer (simple-strategy, risk)

```python
from tradingcz.sdk import TradingApp                     # ← start here

from tradingcz.sdk.market_data import StockDataClient, TimeKeeper
from tradingcz.sdk.account import SignalPublisher
from tradingcz.sdk.indicators import calculate_atr
from tradingcz.sdk.patterns import Retry

from tradingcz.sdk.models.market import Bar, StreamQuote
from tradingcz.sdk.models.enums import Timeframe, OrderSide
from tradingcz.sdk.models.orders import OtoOrderRequest
from tradingcz.sdk.models.events import ExecutionRequestEvent

from tradingcz.sdk.exceptions import SdkError
from tradingcz.sdk.logging import setup_logging
```

### Provider developer (ingestion, executor)

```python
from tradingcz.sdk import ServiceApp                    # ← start here

from tradingcz.sdk.health import HealthMonitor
from tradingcz.sdk.market_data import StockDataClient    # internal use

from tradingcz.sdk.models.enums import EventType, Broker
from tradingcz.sdk.models.events import DataRequest, DataReady, DataError
from tradingcz.sdk.models.headers import EventHeaders, DataHeaders
```

### Power user (advanced messaging)

```python
from tradingcz.sdk._messaging import TypedProducer, EventRouter
from tradingcz.sdk._transport import KafkaChannel, TopicRegistry
```

---

## Move Summary

| Current | New | Notes |
|---|---|---|
| `service.py` + `trading/service.py` | → `service_app.py` | **Merged.** Single source of truth. |
| `trading/app.py` | → `trading_app.py` | Renamed for clarity. |
| `trading/_base.py` | → `market_data/_base.py` | Belongs with data clients. |
| `trading/stock.py` | → `market_data/stock.py` | |
| `trading/options.py` | → `market_data/options.py` | |
| `trading/corporate.py` | → `market_data/corporate.py` | |
| `trading/account.py` | → `account/balance.py` + `account/orders.py` + `account/positions.py` | Split 192-line monolith into three ~60-line files. |
| `trading/signals.py` | → `account/signals.py` | |
| `trading/time_keeper.py` | → `market_data/clock.py` | Market hours are market metadata, not account state. |
| `observability/health.py` (HealthMonitor) | → `health/monitor.py` | |
| `observability/health.py` (HealthPublisher) | → `_messaging/health_publisher.py` | Internal — used only by ServiceApp. |
| `observability/metrics.py` | → **MOVE to executor repo** | Executor-specific Prometheus metrics. |
| `indicators/atr.py` | → `indicators/atr.py` | Unchanged. |
| `patterns/registry.py` | → `patterns/registry.py` | Unchanged. Public, stable. |
| `patterns/retry.py` | → `patterns/retry.py` | Unchanged. Public, stable. |
| `exceptions/errors.py` | → `exceptions.py` | Flatten to root. |
| `logging/logger.py` | → `logging.py` | Flatten to root. Merge with LoggingSettings. |
| `config/config.py` (KafkaSettings) | → `_transport/settings.py` | Configures transport — lives with it. |
| `config/config.py` (AlpacaSettings) | → **MOVE to ingestion repo** | Vendor config. |
| `config/config.py` (LoggingSettings) | → `logging.py` | Merge with logging module. |
| `transport/kafka.py` | → `_transport/channel.py` + `_transport/transport.py` | Split 339-line monolith. |
| `transport/message.py` | → `_transport/message.py` | |
| `transport/topics.py` | → `_transport/topics.py` | |
| `transport/dedup.py` | → `_transport/dedup.py` | |
| `transport/exchange.py` + `messaging/request_reply.py` | → `_messaging/request_reply.py` | **Merged.** Single file with both `RequestReply` and `RequestReplyClient`. |
| `transport/publish.py` | → `_messaging/fire_and_forget.py` | |
| `transport/recovery.py` | → **DELETED** | Duplicate of `messaging/recovery.py` with broken `core.*` imports. |
| `messaging/consumer.py` | → `_messaging/typed.py` | File contains TypedProducer/Consumer/Parser. |
| `messaging/router.py` | → `_messaging/router.py` | |
| `messaging/recovery.py` | → `_messaging/recovery.py` | Canonical copy. |
| `serialization/protocol.py` | → `_serialization/protocol.py` | |
| `serialization/json_codec.py` | → `_serialization/json.py` | Shorter name. |

---

## Deletions

| Item | Reason |
|---|---|
| `service.py` | Duplicate of `trading/service.py` |
| `trading/service.py` | Merged into `service_app.py` |
| `transport/recovery.py` | Duplicate with broken imports |
| `trading/` (entire package) | Redistributed to `market_data/`, `account/`, root |
| `observability/` (entire package) | Redistributed to `health/`, `_messaging/`, executor repo |
| `config/` (entire package) | Redistributed to `_transport/`, `logging.py`, ingestion repo |
| `exceptions/` (entire package) | Flattened to `exceptions.py` |
| `logging/` (entire package) | Flattened to `logging.py` |
| `messaging/` (entire package) | Moved to `_messaging/` |
| `transport/` (entire package) | Moved to `_transport/` |
| `serialization/` (entire package) | Moved to `_serialization/` |
| `patterns/` (old location) | Moved to new `patterns/` (unchanged content) |
| `tradingcz/model/` (empty) | Stale directory |
| `tradingcz/sdk/clients/` (empty) | Stale |
| `tradingcz/sdk/clients/data/` (empty) | Stale |
| `tradingcz/sdk/common/` (empty) | Stale |
| `tradingcz/sdk/core/` (empty) | Stale |
| `tradingcz/sdk/core/messaging/` (empty) | Stale |
| `tradingcz/sdk/core/serialization/` (empty) | Stale |
| `tradingcz/sdk/core/transport/` (empty) | Stale |
| `tradingcz/sdk/data/` (empty) | Stale |
| `tradingcz/sdk/framework/` (empty) | Stale |
| `tradingcz/sdk/models/executor/` (empty) | Stale |
| `models/orders/__init__.py` | Empty — rewrite with proper exports |
| All `__pycache__/` in deleted dirs | Stale cache |
| `extend_path` / `generated/` logic in `__init__.py` files | Dead code |


---

## Migration Path

### Phase 1 — SDK: Create new structure (no deletions yet)

**Goal:** New directories and files exist side-by-side with old ones. All tests pass. Old imports still work.

1. **Create new directory layout:**
   ```bash
   mkdir -p tradingcz/sdk/{market_data,account,health,indicators,patterns}
   mkdir -p tradingcz/sdk/{_messaging,_transport,_serialization}
   ```

2. **Move & adapt files layer by layer (bottom-up):**
   - **Layer 1** — `_transport/`: Copy `transport/*` → `_transport/*`, split `kafka.py` into `channel.py` + `transport.py`, move `config/config.py` KafkaSettings → `_transport/settings.py`. Fix internal imports to use new `_transport` paths.
   - **Layer 2** — `_messaging/`: Copy `messaging/*` → `_messaging/*`, merge `transport/exchange.py` + `messaging/request_reply.py` → `_messaging/request_reply.py`, move `transport/publish.py` → `_messaging/fire_and_forget.py`, rename `consumer.py` → `typed.py`. Fix imports.
   - **Hidden** — `_serialization/`: Copy `serialization/*` → `_serialization/*`, rename `json_codec.py` → `json.py`.
   - **Layer 3** — Public domain packages: Create files per the Future Tree. Update internal imports to use `_messaging` and `_transport`.
   - **Layer 4** — Root app classes: Create `service_app.py` (merged), `trading_app.py`, `exceptions.py`, `logging.py`. Update `__init__.py`.

3. **Verify SDK internally:**
   ```bash
   python -m pylint tradingcz/sdk/ --disable=import-error
   python -m mypy tradingcz/sdk/
   pytest tests/ -v
   ```

4. **Commit on feature branch:**
   ```
   git checkout -b restructure/sdk-layered-domain
   git add tradingcz/sdk/ tests/
   git commit -m "sdk: create new layered domain-driven structure"
   ```

### Phase 2 — Consumer repos: Update imports

**Goal:** Every repo that imports from `tradingcz.sdk` is updated to the new paths.

| Repo | Branch | Key imports to update |
|---|---|---|
| **simple-strategy** | Current branch | `tradingcz.sdk.framework` → `tradingcz.sdk`; `tradingcz.sdk.indicators` → unchanged; `tradingcz.sdk.models.*` → unchanged |
| **ingestion** | `feature/validate-request-types` | `tradingcz.sdk.core.transport.kafka` → `tradingcz.sdk._transport`; `tradingcz.sdk.core.messaging` → `tradingcz.sdk._messaging`; `tradingcz.sdk.framework.service` → `tradingcz.sdk`; `tradingcz.sdk.common.config` → `tradingcz.sdk._transport.settings`; `tradingcz.sdk.common.registry` → `tradingcz.sdk.patterns`; `tradingcz.sdk.models.health` → `tradingcz.sdk.health` |
| **executor** | `main` | Same pattern as ingestion |
| **risk** | `feature/fix6` | `tradingcz.sdk.framework.service` → `tradingcz.sdk`; `tradingcz.sdk.core.messaging` → `tradingcz.sdk._messaging` |
| **testing** | `feature/stress-test-streaming` | `tradingcz.sdk.models.health` → `tradingcz.sdk.health`; other model imports unchanged |

**Per-repo checklist:**
```bash
# 1. Create branch
git checkout -b chore/update-sdk-imports

# 2. Update pyproject.toml to point to SDK restructure branch (temporary)
#    [tool.hatch.build.targets.wheel]
#    packages = ["tradingcz"]

# 3. Find & replace old imports → new imports
grep -r "from tradingcz.sdk" tradingcz/ tests/ | grep -v ".pyc"

# 4. Verify
python -m pylint tradingcz/ --disable=import-error
python -m mypy tradingcz/
pytest tests/ -v

# 5. PR + merge
```

### Phase 3 — SDK: Delete old structure

**Goal:** Remove all old directories and files. Only the new structure remains.

1. **Delete old packages:**
   ```bash
   rm -rf tradingcz/sdk/service.py          # duplicate
   rm -rf tradingcz/sdk/trading/            # redistributed
   rm -rf tradingcz/sdk/observability/      # redistributed
   rm -rf tradingcz/sdk/config/             # redistributed
   rm -rf tradingcz/sdk/exceptions/         # flattened to exceptions.py
   rm -rf tradingcz/sdk/logging/            # flattened to logging.py
   rm -rf tradingcz/sdk/messaging/          # moved to _messaging/
   rm -rf tradingcz/sdk/transport/          # moved to _transport/
   rm -rf tradingcz/sdk/serialization/      # moved to _serialization/
   rm -rf tradingcz/sdk/patterns/           # moved to new patterns/
   ```

2. **Delete stale empty directories:**
   ```bash
   rm -rf tradingcz/sdk/clients/
   rm -rf tradingcz/sdk/common/
   rm -rf tradingcz/sdk/core/
   rm -rf tradingcz/sdk/data/
   rm -rf tradingcz/sdk/framework/
   rm -rf tradingcz/sdk/models/executor/
   rm -rf tradingcz/model/
   ```

3. **Clean stale `__pycache__`:**
   ```bash
   find tradingcz/ -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
   ```

4. **Verify:**
   ```bash
   python -m pylint tradingcz/sdk/ --disable=import-error
   pytest tests/ -v
   find tradingcz/sdk/ -type d | sort  # should match Future Tree exactly
   ```

5. **Commit & merge to main:**
   ```
   git add -A tradingcz/sdk/ tradingcz/model/
   git commit -m "sdk: remove old structure, finalize layered domain-driven layout"
   gh pr create --base main --title "sdk: layered domain-driven restructure"
   ```

### Phase 4 — Consumer repos: Point back to SDK main

**Goal:** All consumer repos use the released SDK from main (not the feature branch).

1. **Update `pyproject.toml`** in each repo to use the released SDK version
2. **Final verification** — full CI/CD pipeline across all repos:
   ```bash
   # In each consumer repo:
   pip install trading-sdk==<new-version>
   pytest tests/ -v
   python -m pylint tradingcz/ --disable=import-error
   ```

### Phase 5 — Cross-repo integration test

**Goal:** End-to-end verification that all services work together with the new SDK structure.

```bash
# From testing repo:
docker compose up -d    # start Kafka + simulator
pytest tests/integration/ -v
pytest tests/regression/ -v
pytest tests/stress/ -v
docker compose down
```

### Rollback Plan

If anything breaks in Phase 2 or 3:

1. Revert the SDK commit: `git revert <commit>`
2. Revert each consumer repo's import-update commit
3. Old structure is fully intact (we never deleted in Phase 1)

**Key safety property:** Phase 1 creates new structure WITHOUT deleting old. All old imports continue to work until Phase 3. Rollback at any point before Phase 3 is a simple `git revert`.
