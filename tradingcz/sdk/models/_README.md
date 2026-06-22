# Models Package

Canonical data models shared across all services (ingestion, executor, risk,
strategies). The single source of truth for the Kafka wire format.

```text
models/
├── enums/       # StrEnum definitions — wire-safe string constants
├── events/      # Kafka event payload DTOs (DataRequest, ExecutionRequest, etc.)
├── market/      # Market data DTOs (Bar, Quote, Trade, Snapshot, etc.)
└── orders/      # Order request DTOs (MarketOrder, LimitOrder, BracketOrder, etc.)
```

---

## enums/ — What Each Subfile Is For

All enums are `StrEnum`; Pydantic validates against them at deserialization time.

### `adjustment.py`

**`Adjustment`** — how ingestion should normalize bar OHLCV data for corporate
actions (splits, dividends). Passed in `DataRequest` events and historical bar
API queries.

### `event.py`

The platform's core routing & lifecycle enums:

- **`EventType`** — Kafka `message_type` header and `event_type` payload field.
  Distinguishes control-plane signals, trading signals, service responses, and
  market data.
- **`EventStatus`** — event workflow state machine. Tracks each event from
  receipt through processing, execution, market exposure, to terminal state.
- **`StrategyType`** — strategy family identifier. Used to correlate events
  and orders back to their originating strategy.
- **`ServiceRequestType`** — cross-service RPC commands (request positions,
  orders, balances). Processed by executor.

Also re-exports `AssetType`, `Broker`, `DataRequestType`, `LifecycleEventType`,
`MarketDataType` — see the file for their current definitions.

### `order.py`

Everything related to order placement, routing, and lifecycle:

- **`OrderSide`** — buy vs. sell.
- **`OrderType`** — execution semantics (market, limit, stop, etc.).
- **`OrderClass`** — order complexity (simple, bracket, OCO, OTO, multi-leg).
- **`TimeInForce`** — order duration (day, GTC, IOC, FOK, etc.).
- **`OrderStatus`** — full order lifecycle state machine. `TERMINAL_STATUSES`
  is a `frozenset` of the terminal states; use for completion/is-done checks.
- **`SortOrder`** — time-series direction (ascending for backtesting,
  descending for latest-N queries).

The executor normalizes broker-specific statuses into these enums.

### `timeframe.py`

**`Timeframe`** — canonical bar timeframe. The wire contract between strategies
and ingestion (format: `"1min"`, `"4h"`, `"1d"`, `"1week"`, `"1month"`).
Pydantic rejects non-canonical variants. Every `DataRequest` carries a
`Timeframe` value; ingestion maps it to the provider-specific format.
