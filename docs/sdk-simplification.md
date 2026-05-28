# SDK Simplification — Final Design

> **Date:** 2026-05-28
> **Branch:** `feature/simplification-sdk`
> **Decision:** Kafka permanent. Remove transport ABCs. Add business-layer clients. Headers for metadata. Plain-string keys for routing.

---

## Table of Contents

1. [Core Principles](#core-principles)
2. [Three-Topic Architecture](#three-topic-architecture)
3. [Client Architecture](#client-architecture)
4. [Internal Helpers (Not Public)](#internal-helpers-not-public)
5. [Topics: Key / Value / Headers Design](#topics-key--value--headers-design)
6. [TradingApp Builder](#tradingapp-builder)
7. [Client Specifications](#client-specifications)
8. [File Structure After Refactor](#file-structure-after-refactor)
9. [What Gets Removed](#what-gets-removed)
10. [Implementation Phases](#implementation-phases)

---

## Core Principles

| Principle | Meaning |
|-----------|---------|
| **Kafka is permanent** | No `Channel`/`Transport` ABCs. `KafkaChannel`/`KafkaTransport` are the concrete foundation. |
| **Users write business logic** | One import, one builder, typed methods like `stream_quotes()`, `get_positions()`. Zero Kafka knowledge. |
| **Concrete specialized clients** | `DataClient`, `SignalPublisher`, `PositionClient`, `BalanceClient` — each has precise, narrow methods. Internally they reuse `_RequestReply` and `_FireAndForget` helpers. |
| **Headers = metadata, Key = routing, Value = payload** | Three cleanly separated concerns per Kafka message. |
| **No self-typing in value** | Message type is in the header (`message_type`). Value is pure domain payload — no `event_type` discriminator field. |
| **Sequence numbers in headers** | Every message gets `sequence` (monotonic per source). Guarantees ordering even with timestamp collisions. |
| **Serialization ABCs stay** | `Serializer`/`Deserializer`/`Codec` are pure data conversion. Transport-independent. Useful for future non-JSON formats. |
| **Performance uncompromised** | Business layer is zero-cost wrappers. Same `AIOProducer`/`AIOConsumer` underneath. |

---

## Three-Topic Architecture

The system has exactly three topics. All control-plane and signal messages share the event topic. No separate signal topic.

```
┌─────────────────┐    ┌──────────────────┐    ┌───────────────────────────┐
│   dev-event      │    │  dev-market-data  │    │  dev-market-data-         │
│   1 partition    │    │  N partitions     │    │  historical-{request_id}  │
│                  │    │                   │    │  1 partition              │
│   DataRequest    │    │  Trade            │    │                           │
│   DataReady      │    │  Quote            │    │  Bar                      │
│   DataError      │    │  StreamQuote      │    │                           │
│   TradingSignal  │    │  Bar              │    │                           │
│   ServiceRequest │    │                   │    │                           │
│   PositionList   │    │                   │    │                           │
│   BalanceResp    │    │                   │    │                           │
│   ...            │    │                   │    │                           │
└─────────────────┘    └──────────────────┘    └───────────────────────────┘
    Control plane          Streaming data           Ephemeral (per-request)
    Request/reply          Keyed by symbol           Keyed by symbol
    Fire-and-forget        High volume               Low volume
```

**Why one event topic?** Intentional — operational simplicity. One ACL, one retention policy, one place to monitor. Total ordering via single partition. Volume is hundreds/day — splitting is premature.

**Why one ephemeral historical partition?** Low volume (max thousands/hour). Single consumer per request. Timestamp ordering via sequence numbers — partitions aren't needed for parallelism.

---

## Client Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  PUBLIC API (what users import and use)                      │
│                                                              │
│  TradingApp  — builder, one-stop setup                       │
│  ├── DataClient       — stream_quotes, request_historical    │
│  ├── SignalPublisher  — publish(trading_signal)              │
│  ├── PositionClient   — get_positions, get_position          │
│  ├── BalanceClient    — get_balance, get_buying_power        │
│  └── OrderClient      — get_orders, get_order_status         │
│                                                              │
│  All clients are concrete. Each has specific typed methods.  │
│  Users see domain operations, never Kafka internals.         │
├──────────────────────────────────────────────────────────────┤
│  INTERNAL HELPERS (used by clients, NOT exported publicly)   │
│                                                              │
│  _RequestReply  — send request, await correlated response    │
│  _FireAndForget — send message, don't wait                   │
│  _StreamFanout  — single consumer → multiple async iterators │
│                                                              │
│  These are the "base types" that eliminate code duplication. │
│  Users NEVER import them directly.                           │
├──────────────────────────────────────────────────────────────┤
│  TYPED LAYER (public for power users)                        │
│                                                              │
│  TypedProducer[T]   — send typed values                      │
│  TypedConsumer[T]   — consume typed values                   │
│  TypedParser        — header-based dispatch to model types   │
├──────────────────────────────────────────────────────────────┤
│  KAFKA LAYER (concrete, no ABCs)                             │
│                                                              │
│  KafkaChannel       — send/receive with headers              │
│  KafkaTransport     — channel factory + shared producer      │
│  KafkaMessage       — honest wrapper (offset, partition etc) │
│  TopicRegistry      — topic naming + header factories        │
├──────────────────────────────────────────────────────────────┤
│  SERIALIZATION (abstract, pure data)                         │
│                                                              │
│  Serializer / Deserializer / Codec  [ABCs]                   │
│  JsonCodec[T]                                                    │
├──────────────────────────────────────────────────────────────┤
│  MODELS (pure Pydantic, no I/O, no transport)                │
│                                                              │
│  Bar, Trade, Quote, StreamQuote, TradingSignal,              │
│  DataRequest, DataReady, DataError, ServiceRequest,          │
│  Position, Balance, OrderStatus, ...                         │
└──────────────────────────────────────────────────────────────┘
```

### Clients reuse internal helpers — example

```python
# Internal — not exported
class _RequestReply:
    """Send a typed request, await correlated typed response.

    Used internally by: DataClient, PositionClient, BalanceClient, OrderClient.
    """
    def __init__(self, channel: KafkaChannel, service_id: str): ...

    async def request[Req: BaseModel, Resp: BaseModel](
        self,
        req: Req,
        *,
        response_type: type[Resp],
        timeout: float = 30.0,
    ) -> Resp: ...


class _FireAndForget:
    """Send a typed message, don't wait.

    Used internally by: SignalPublisher, DataClient (for DataRequest when
    the response is handled separately).
    """
    def __init__(self, channel: KafkaChannel, service_id: str): ...

    async def send(self, message: BaseModel, *, message_type: str) -> None: ...


# Public — what users see
class DataClient:
    def __init__(self, rr: _RequestReply, faf: _FireAndForget,
                 transport: KafkaTransport, topics: TopicRegistry): ...

    async def request_historical(self, symbols, *, days=14):
        req = DataRequest(type="historic", symbols=symbols, ...)
        resp = await self._rr.request(req, response_type=DataReady)
        # ... channel management, bar consumption ...


class SignalPublisher:
    def __init__(self, faf: _FireAndForget): ...

    async def publish(self, signal: TradingSignal, *, tracking_id: str):
        await self._faf.send(signal, message_type="trading_signal")
```

---

## Topics: Key / Value / Headers Design

### Event topic (`dev-event`, 1 partition)

```
Key:     (not set — 1 partition, routing is moot)
Headers:
  message_type: "data_request"          ← WHAT class to deserialize into
  source_app: "strategy-atr3"           ← WHO sent it
  request_id: "abc123"                  ← correlation (present for req/reply, absent for fire-and-forget)
  schema_version: "1.0"                 ← schema evolution
  sequence: "1"                         ← monotonic per source_app (ordering)
Value:   {"symbols":["AAPL"],"type":"historic","timeframe":"1d",...}
         ↑ pure domain payload — no event_type field
```

**Why no `event_type` in value?** The `message_type` header already tells the consumer which Pydantic model to deserialize into. Putting the same string in the value is redundant. The class name (DataRequest) is the type — no discriminator field needed.

**How does parsing work?** A type registry maps `message_type` → model class:

```python
_MESSAGE_TYPES: dict[str, type[BaseModel]] = {
    "data_request": DataRequest,
    "data_ready": DataReady,
    "data_error": DataError,
    "trading_signal": TradingSignal,
    "service_request": ServiceRequest,
    "position_response": PositionList,
    "balance_response": BalanceResponse,
    # ... registered by each client at init time
}

def parse_message(message_type: str, payload: bytes) -> BaseModel:
    model_type = _MESSAGE_TYPES[message_type]
    return model_type.model_validate_json(payload)
```

**What about `_RequestReply` correlation?** The helper reads `request_id` from both the request model AND the response model. Since `DataRequest`, `DataReady`, `DataError` all have `request_id: str`, the helper extracts it generically via `getattr(msg, "request_id")`. This convention-based approach avoids the need for explicit `request_id_of` / `response_id_of` callbacks.

### Stream topic (`dev-market-data`, N partitions)

```
Key:     "AAPL"                         ← plain symbol, UTF-8, for partition co-location
Headers:
  message_type: "trade"                 ← "trade" | "quote" | "bar"
  source: "ingestion"
  broker: "alpaca"
  symbol: "AAPL"                        ← also in value for self-contained deserialization
  schema_version: "1.0"
  sequence: "42"                        ← per-symbol, per-message_type monotonic
Value:   {"symbol":"AAPL","price":150.25,"size":100,"timestamp":"...",...}
```

**Why symbol in key AND header AND value?**
- **Key:** For Kafka partition routing. Plain string, Murmur2 hashed.
- **Header:** For filtering without deserializing the value (e.g., skip non-AAPL messages in consumer loop).
- **Value:** For self-contained Pydantic deserialization. The model is complete without reading headers.

This is a deliberate minor duplication. Each copy serves a different layer and a different consumer.

### Historical topic (`dev-market-data-historical-{request_id}`, 1 partition)

```
Key:     "AAPL"                         ← same pattern as stream, for consistency
Headers:
  message_type: "bar"
  source: "ingestion"
  broker: "alpaca"
  request_id: "abc123"                  ← consumer filters by this
  schema_version: "1.0"
  sequence: "1"                         ← ordering within this request
Value:   {"symbol":"AAPL","open":150.0,"high":152.0,...}
```

**Consumer filtering:** Read all messages from the channel. Skip any where `headers["request_id"] != my_request_id`. Sort remaining by `sequence`. This is safe because `KafkaChannel.receive()` preserves partition ordering, and we have 1 partition.

### Sequence number design

Every message on every topic gets a `sequence` header. The sequence is:

- **Monotonic per `(source_app, topic)`** — resets on restart is acceptable (it's for ordering, not global uniqueness).
- **String-formatted integer** — headers are `str → str` in our design, so `"1"`, `"2"`, etc.
- **Consumed for ordering, not deduplication** — consumers sort by sequence when reading from multiple partitions or historical topics. The sequence guarantees correct order even when timestamps collide.

Who assigns sequences?
- **Ingestion** assigns sequences for market-data and historical messages.
- **SDK `_FireAndForget` and `_RequestReply`** assign sequences for event topic messages (monotonic counter per client instance).

---

## TradingApp Builder

```python
"""The single entry point for SDK consumers.

Usage — all features enabled by default:
    from tradingcz.sdk import TradingApp

    app = (TradingApp(env="dev", service_id="my-strategy")
           .build())
    await app.start()

    # Business-level APIs:
    bars = await app.data.request_historical(["AAPL"])
    async for quote in app.data.stream_quotes(["TSLA"]):
        ...
    positions = await app.positions.get_positions()

    await app.close()

Usage — selective features:
    app = (TradingApp(env="dev", service_id="risk-checker")
           .with_data(False)
           .with_signals(False)
           .build())
    await app.start()
    # Only app.positions, app.balance, app.orders available
"""

class TradingApp:
    """Builder for a fully wired trading application."""

    def __init__(self, *, env: str = "dev", service_id: str,
                 bootstrap_servers: str = "localhost:9092"):
        self._env = env
        self._service_id = service_id
        self._bootstrap_servers = bootstrap_servers
        self._enable_data = True
        self._enable_signals = True
        self._enable_positions = True
        self._enable_balance = True
        self._enable_orders = True

    def with_data(self, enable: bool = True) -> "TradingApp": ...
    def with_signals(self, enable: bool = True) -> "TradingApp": ...
    def with_positions(self, enable: bool = True) -> "TradingApp": ...
    def with_balance(self, enable: bool = True) -> "TradingApp": ...
    def with_orders(self, enable: bool = True) -> "TradingApp": ...

    def build(self) -> "TradingApp":
        """Validate and freeze configuration. Call before start()."""
        ...

    async def start(self) -> None:
        """Initialize transport and enabled clients."""
        ...

    async def close(self) -> None:
        """Graceful shutdown."""
        ...

    # Public attributes (available after start())
    data: DataClient | None
    signals: SignalPublisher | None
    positions: PositionClient | None
    balance: BalanceClient | None
    orders: OrderClient | None
```

---

## Client Specifications

### DataClient

```python
class DataClient:
    """Request and consume market data (historical + streaming).

    Handles the full lifecycle:
      1. Send DataRequest via event topic (_RequestReply)
      2. Await DataReady (contains data_topic for historical,
         or market_data topic for streaming)
      3. Manage ephemeral channel or subscribe to stream channel
      4. Filter, order, parse, and yield typed results
    """

    async def request_historical(
        self,
        symbols: list[str],
        *,
        days: int = 14,
        timeframe: str = "1d",
        broker: str = "alpaca",
        timeout: float = 30.0,
    ) -> dict[str, list[Bar]]:
        """Request historical daily bars.

        Returns: {symbol: [Bar sorted by timestamp]}
        """

    async def stream_quotes(
        self,
        symbols: list[str],
        *,
        broker: str = "alpaca",
        timeout: float = 30.0,
    ) -> AsyncIterator[StreamQuote]:
        """Stream live quotes. Yields StreamQuote objects."""

    async def stream_trades(
        self,
        symbols: list[str],
        *,
        broker: str = "alpaca",
        timeout: float = 30.0,
    ) -> AsyncIterator[Trade]:
        """Stream live trades. Yields Trade objects."""

    # Internal: stream_quotes and stream_trades share one underlying
    # consumer via _StreamFanout. Users can call both simultaneously.
```

**Simultaneous streams:** When a user calls both `stream_quotes` and `stream_trades`, the first call sends a `DataRequest` with both stream types and starts the internal consumer loop. The second call registers an additional handler. Both iterators receive their respective message types from the same Kafka consumer — no duplicate broker subscriptions.

### SignalPublisher

```python
class SignalPublisher:
    """Publish trading signals (fire-and-forget on event topic)."""

    async def publish(
        self,
        signal: TradingSignal,
        *,
        tracking_id: str,
    ) -> None:
        """Publish a trading signal.

        Sends to the event topic with:
          message_type = "trading_signal"
          key = signal.symbol
        """
```

### PositionClient

```python
class PositionClient:
    """Query open positions via event topic (request/reply)."""

    async def get_positions(self) -> list[Position]:
        """Return all currently open positions."""

    async def get_position(self, symbol: str) -> Position | None:
        """Return position for a single symbol, or None."""


class Position(BaseModel):
    """A single open position."""
    model_config = ConfigDict(frozen=True)
    symbol: str
    qty: float
    avg_entry_price: float
    asset_type: Literal["stock", "option"] = "stock"


class PositionList(BaseModel):
    """Response to a get_positions request."""
    request_id: str
    positions: list[Position]
    source_app: str = "executor"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

### BalanceClient

```python
class BalanceClient:
    """Query account balance via event topic (request/reply)."""

    async def get_balance(self) -> Balance:
        """Return current account balance."""

    async def get_buying_power(self) -> float:
        """Return available buying power (convenience)."""


class Balance(BaseModel):
    """Account balance snapshot."""
    model_config = ConfigDict(frozen=True)
    cash: float
    buying_power: float
    portfolio_value: float
    currency: str = "USD"


class BalanceResponse(BaseModel):
    """Response to a balance query."""
    request_id: str
    balance: Balance
    source_app: str = "executor"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

### OrderClient

```python
class OrderClient:
    """Query order status via event topic (request/reply)."""

    async def get_orders(
        self, *, status: str | None = None, symbol: str | None = None
    ) -> list[OrderSummary]:
        """Return orders, optionally filtered by status or symbol."""

    async def get_order_status(self, order_id: str) -> OrderSummary | None:
        """Return status of a single order."""
```

### ServiceRequest — the unified request model

All position/balance/order queries share one request model:

```python
class ServiceRequest(BaseModel):
    """General-purpose request to the executor service.

    Sent on the event topic with message_type = "service_request".
    The executor responds with the corresponding response type
    (PositionList, BalanceResponse, OrderList, etc.).
    """
    request_id: str = Field(default_factory=lambda: uuid4().hex)
    source_app: str = ""
    service: Literal[
        "get_positions",
        "get_position",
        "get_balance",
        "get_buying_power",
        "get_orders",
        "get_order_status",
    ]
    symbol: str | None = None
    order_id: str | None = None
    order_status: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

---

## Internal Helpers (Not Public)

These are the reusable "base types" that all clients share. They are NOT exported from `tradingcz.sdk`. Documented here for maintainers.

### `_RequestReply`

```python
class _RequestReply:
    """Send a typed request on the event topic, await a correlated response.

    Correlation is by `request_id` — both request and response models
    must have a `request_id: str` field (enforced by convention, not by Protocol).

    The `message_type` header on the response is used to dispatch to the
    correct Pydantic model for deserialization.
    """

    def __init__(self, channel: KafkaChannel, service_id: str, *,
                 message_types: dict[str, type[BaseModel]] | None = None):
        self._channel = channel
        self._service_id = service_id
        self._seq = 0  # monotonic sequence counter
        self._types = message_types or {}
        self._pending: dict[str, asyncio.Future[BaseModel]] = {}
        self._listen_task: asyncio.Task | None = None

    def register_type(self, message_type: str, model: type[BaseModel]) -> None:
        """Register a message_type → model mapping for deserialization."""
        self._types[message_type] = model

    async def start(self) -> None:
        """Start the background listener (idempotent)."""

    async def request[Resp: BaseModel](
        self, req: BaseModel, *, response_type: type[Resp], timeout: float = 30.0,
    ) -> Resp:
        """Send *req*, wait for a correlated *Resp*.

        The request model must have `request_id: str`.
        Responses are matched by request_id.
        Non-matching messages (other services' traffic on the event topic)
        are silently skipped with a debug log.
        """
        self._seq += 1
        headers = {
            "message_type": self._infer_type(req),
            "source_app": self._service_id,
            "request_id": req.request_id,
            "schema_version": SCHEMA_VERSION,
            "sequence": str(self._seq),
        }
        payload = req.model_dump_json().encode()
        await self._channel.send(payload, key="", headers=headers)
        # ... await future, match by request_id ...

    async def close(self) -> None: ...

    @staticmethod
    def _infer_type(model: BaseModel) -> str:
        """Infer message_type from model class name → snake_case."""
        # DataRequest → "data_request"
        return re.sub(r'(?<!^)(?=[A-Z])', '_', type(model).__name__).lower()
```

### `_FireAndForget`

```python
class _FireAndForget:
    """Send a typed message on the event topic. No response expected."""

    def __init__(self, channel: KafkaChannel, service_id: str):
        self._channel = channel
        self._service_id = service_id
        self._seq = 0

    async def send(self, message: BaseModel, *, message_type: str) -> None:
        self._seq += 1
        headers = {
            "message_type": message_type,
            "source_app": self._service_id,
            "schema_version": SCHEMA_VERSION,
            "sequence": str(self._seq),
        }
        payload = message.model_dump_json().encode()
        await self._channel.send(payload, key="", headers=headers)
```

---

## File Structure After Refactor

```
tradingcz/
├── __init__.py              # SCHEMA_VERSION = "1.0"
├── py.typed
│
├── sdk/                     # NEW — business layer
│   ├── __init__.py          # exports: TradingApp
│   ├── _app.py              # TradingApp builder
│   ├── _helpers.py          # _RequestReply, _FireAndForget, _StreamFanout (INTERNAL)
│   ├── data.py              # DataClient
│   ├── signals.py           # SignalPublisher
│   ├── positions.py         # PositionClient, Position, PositionList
│   ├── balance.py           # BalanceClient, Balance, BalanceResponse
│   └── orders.py            # OrderClient, OrderSummary
│
├── transport/               # SIMPLIFIED — Kafka-concrete
│   ├── __init__.py          # exports: KafkaChannel, KafkaTransport, KafkaMessage, ...
│   ├── kafka_channel.py     # KafkaChannel + KafkaTransport (with headers)
│   ├── kafka_message.py     # KafkaMessage dataclass
│   ├── typed.py             # TypedProducer, TypedConsumer, TypedParser
│   ├── topics.py            # TopicRegistry, TopicConfig (+ header factories)
│   └── hash.py              # Murmur2, partition_for()
│
├── serialization/           # UNCHANGED
│   ├── __init__.py
│   ├── protocol.py          # Serializer, Deserializer, Codec ABCs
│   └── json_codec.py        # JsonCodec[T]
│
├── config/                  # UNCHANGED
│   ├── __init__.py
│   └── settings.py          # KafkaSettings
│
├── model/
│   ├── __init__.py
│   ├── enum/                # Unchanged
│   ├── ingestion/           # + StreamQuote model
│   ├── executor/            # Populated __init__.py files
│   ├── events.py            # DataRequest, DataReady, DataError (NO event_type)
│   ├── signal.py            # TradingSignal, SignalKey, SignalValue (NO build_signal)
│   └── message_headers.py   # RENAMED from kafka_key.py — header schema models
│
├── indicators/              # UNCHANGED
│   ├── __init__.py
│   └── atr.py
│
└── errors.py                # NEW — SdkError, TransportError, etc.
```

### Files removed

| File | Reason |
|------|--------|
| `tradingcz/transport/protocol.py` | `Channel`/`Transport`/`Message` ABCs — unnecessary indirection |
| `tradingcz/transport/stream.py` | Merged into `transport/typed.py` |
| `tradingcz/transport/request_reply.py` | Replaced by internal `_RequestReply` helper |
| `tradingcz/model/kafka_key.py` | Renamed to `message_headers.py` |

### Files added

| File | Purpose |
|------|---------|
| `tradingcz/sdk/_app.py` | `TradingApp` builder |
| `tradingcz/sdk/_helpers.py` | `_RequestReply`, `_FireAndForget`, `_StreamFanout` |
| `tradingcz/sdk/data.py` | `DataClient` |
| `tradingcz/sdk/signals.py` | `SignalPublisher` |
| `tradingcz/sdk/positions.py` | `PositionClient` + models |
| `tradingcz/sdk/balance.py` | `BalanceClient` + models |
| `tradingcz/sdk/orders.py` | `OrderClient` + models |
| `tradingcz/transport/kafka_message.py` | `KafkaMessage` dataclass |
| `tradingcz/transport/hash.py` | Murmur2 + `partition_for()` |
| `tradingcz/errors.py` | Shared error types |
| `tradingcz/model/message_headers.py` | Renamed from kafka_key.py |

---

## What Gets Removed

### 1. `Channel` / `Transport` ABCs (`tradingcz/transport/protocol.py`)

No abstract transport layer. `KafkaChannel` and `KafkaTransport` are the direct concrete API. Test with mocks — Python doesn't need ABCs for that.

### 2. `Message` dataclass

Replaced by `KafkaMessage` — an honest Kafka wrapper with `offset`, `partition`, `topic`, `key`, `headers`, `payload`. Named what it is.

### 3. `event_type` discriminator field from all Pydantic models

`DataRequest`, `DataReady`, `DataError` no longer have `event_type: Literal[...]`. Type is identified by `message_type` header. A type registry maps header value → model class.

### 4. `build_signal()` from `tradingcz/model/signal.py`

Moved to `tradingcz/sdk/signals.py` as part of `SignalPublisher.publish()`.

### 5. JSON blob keys

`EventKey` and `MarketDataKey` Pydantic models are removed. Keys are plain strings (`"AAPL"`, `""`). All metadata moves to headers.

### 6. `RequestReplyClient` public class

Replaced by internal `_RequestReply` helper. Users access request/reply through specialized clients (`PositionClient.get_positions()`) — never directly.

---

## Implementation Phases

### Phase 1: Foundation (shared infrastructure)
- [x] Create feature branch `feature/simplification-sdk`
- [ ] Add `tradingcz/errors.py` — shared error hierarchy
- [ ] Add `tradingcz/transport/kafka_message.py` — `KafkaMessage` dataclass
- [ ] Add `tradingcz/transport/hash.py` — Murmur2 + `partition_for()`
- [ ] Update `KafkaChannel.send()` to accept `headers: dict[str, str]`
- [ ] Update `KafkaChannel.receive()` to yield `KafkaMessage` (with headers)
- [ ] Add `SCHEMA_VERSION` to `tradingcz/__init__.py`
- [ ] Remove `event_type` from `DataRequest`, `DataReady`, `DataError`, `TradingSignal`
- [ ] Add `StreamQuote` model to `tradingcz/model/ingestion/`
- [ ] Rename `kafka_key.py` → `message_headers.py` (with deprecation re-export)
- [ ] Populate empty executor model `__init__.py` files
- [ ] Delete outdated tests

### Phase 2: Remove ABCs
- [ ] Remove `tradingcz/transport/protocol.py`
- [ ] Update `TypedProducer`/`TypedConsumer` to use `KafkaChannel` directly
- [ ] Add `TypedParser` — header-based dispatch to model types
- [ ] Merge `stream.py` into `typed.py`

### Phase 3: Add internal helpers
- [ ] Add `tradingcz/sdk/_helpers.py` — `_RequestReply`, `_FireAndForget`
- [ ] Add header factories to `TopicRegistry`

### Phase 4: Add business clients
- [ ] Add `tradingcz/sdk/_app.py` — `TradingApp` builder
- [ ] Add `tradingcz/sdk/data.py` — `DataClient`
- [ ] Add `tradingcz/sdk/signals.py` — `SignalPublisher`
- [ ] Add `tradingcz/sdk/positions.py` — `PositionClient`
- [ ] Add `tradingcz/sdk/balance.py` — `BalanceClient`
- [ ] Add `tradingcz/sdk/orders.py` — `OrderClient`

### Phase 5: Migrate services
- [ ] Migrate `simple-strategy` to use `TradingApp`
- [ ] Migrate `ingestion` to use `TradingApp`
- [ ] Bump `executor` SDK version, adopt shared models
