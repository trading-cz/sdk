# Analysis: New Layer 2.5 — SingleTypeConsumer

**Date**: 2026-06-22  
**Question**: Do we need a new class that only reads/consumes a specific datatype from a topic (no event_type dispatch)?

---

## 1. Current Consumer Hierarchy

```
┌─────────────────────────────────────────────────────────┐
│ Layer 1: TransportConsumer                               │
│ Raw Kafka consumer → yields KafkaMessage (bytes/headers) │
│ No typing, no filtering, no dispatch                     │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│ Layer 2: TypedConsumer                                   │
│ Wraps TransportConsumer                                  │
│ Dispatches by event_type header → Pydantic model         │
│ Yields (event_type, model, raw) tuples                   │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│ Layer 3: Messaging Patterns                              │
│ • EventRouter    — multi-type handler dispatch + filter   │
│ • RequestReply   — request/response by event_id           │
│ • ReplayConsumer — topic replay with sentinel             │
│ • FireAndForget  — produce only (not a consumer)          │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Corrected: Data Topics DO Have `event_type`

**Correction from v1**: `DataHeader` extends `KafkaHeader`, which requires `event_type`. Data topics
DO carry `event_type` headers — so `TypedConsumer` CAN dispatch on them. The reason
`_consume_typed()` uses raw `TransportConsumer` is NOT a header limitation — it's because the
current consumer needs custom filtering (event_id, dedup) that `TypedConsumer` doesn't provide.

```python
# KafkaHeader — base for ALL headers, event_type is ALWAYS present
class KafkaHeader(BaseModel):
    event_type: EventType      # ← always present, even on data topics!
    source_app: str

# DataHeader — extends KafkaHeader, ADDS data-specific fields
class DataHeader(KafkaHeader):
    event_id: str = ""
    sequence: int = 0
    broker: str = ""
    source: str = ""
    symbol: str = ""
```

Ingestion publishes to data topics WITH `event_type`:
```python
# stock_stream.py:_stream_loop()
msg_type = market_item_message_type(item)  # Bar→EventType.BAR, Quote→EventType.QUOTE, etc.
headers = DataHeader(event_type=msg_type, ...)
await self._data_producer.send(item, key=..., headers=headers)
```

So `TypedConsumer` **can** dispatch on data topics — the real design question is different…

---

## 3. The Real Design Question: Per-Type Topics vs Multi-Type Topics

### Current state: Multi-Type Topics

Two topics carry ALL market data types mixed together:

```
┌──────────────────────────────────────────────────┐
│  {env}-stock-market-stream-data   (5 partitions) │
│  Carries: Bar | Quote | Trade | TradingStatus    │
│  Dispatched by: event_type header                │
└──────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────┐
│  {env}-stock-market-historical-data (1 partition)│
│  Carries: Bar | Quote | Trade | Snapshot         │
│  Dispatched by: event_type header                │
└──────────────────────────────────────────────────┘
```

One ingestion pod publishes ALL types to the SAME topic. Consumers filter by `event_type`
header (either via `TypedConsumer` dispatch or manual header check).

### Proposal: Per-Type Topics

Split so each data type gets its own topic:

```
┌─────────────────────────┐  ┌─────────────────────────┐  ┌─────────────────────────┐
│ {env}-stock-stream-bars │  │{env}-stock-stream-quotes│  │{env}-stock-stream-trades│
│ (1 part, long retention)│  │ (5 part, short retention)│  │ (3 part, medium ret)    │
└─────────────────────────┘  └─────────────────────────┘  └─────────────────────────┘
┌─────────────────────────┐  ┌─────────────────────────┐  ┌─────────────────────────┐
│ {env}-stock-hist-bars   │  │{env}-stock-hist-quotes  │  │{env}-stock-hist-trades  │
│ (1 partition)           │  │ (1 partition)           │  │ (1 partition)           │
└─────────────────────────┘  └─────────────────────────┘  └─────────────────────────┘
```

### Alpaca Stream Reference (broker-agnostic pattern)

Alpaca's `StockDataStream` demuxes by type at the callback level — each data type has its own
subscribe method. This is the **universal pattern** across brokers (Polygon, IB, etc.):

| Alpaca callback | Data type | Relative volume | Consumer need |
|---|---|---|---|
| `subscribe_quotes()` | Quote | 🔴 Very high (100s-1000s/sec) | May want latest-only or every tick |
| `subscribe_trades()` | Trade | 🟡 Medium | Conditions, price, volume filtering |
| `subscribe_bars()` | Bar (minute) | 🟢 Low (~1/min/symbol) | Want every bar |
| `subscribe_daily_bars()` | Bar (daily) | 🟢 Very low (~1/day) | Want every bar |
| `subscribe_updated_bars()` | Bar (updated) | 🟢 Low | Real-time bar updates |
| `subscribe_trading_statuses()` | TradingStatus | ⚪ Rare | Halt/resume events |

### Recommendation: **Split into per-type topics**

**Reasoning:**

1. **Volume isolation is the killer argument.** Quotes at 1000/sec should never congest
   bars at 1/min. On a multi-type topic, a bar consumer must receive, deserialize headers,
   and discard every quote message. With per-type topics, the bar consumer subscribes only
   to the bars topic and never sees quotes.

2. **Independent topic configuration.** Quotes topic: many partitions, short retention
   (high throughput, data is ephemeral). Bars topic: few partitions, long retention
   (low throughput, data is valuable for analysis). Can't do this on a shared topic.

3. **Natural demux point already exists.** The Alpaca adapter has per-type callbacks
   (`subscribe_quotes`, `subscribe_trades`, `subscribe_bars`). Publishing to separate
   topics at that point is trivial — one `TypedProducer` per type. The ingestion pod
   already runs asyncio; writing to 3 topics is just 3 `await producer.send()` calls.

4. **Broker-agnostic.** All market data providers (Alpaca, Polygon, IB, Schwab) have the
   same type taxonomy: quotes, trades, bars/aggregates. This isn't Alpaca-specific.

5. **Consumer simplicity.** A consumer wanting bars subscribes to `{env}-stock-stream-bars`
   and knows every message is a `Bar`. No type dispatch needed. No filtering out
   quotes/trades. `DataTopicConsumer` becomes genuinely single-type.

6. **Multi-type consumers still possible.** A consumer wanting both quotes AND trades
   creates two `DataTopicConsumer` instances (one per topic). The overhead is acceptable
   for the rare case; the common case (single type) gets the clean path.

### Cost: ~3 more topics per environment

| Scenario | Stream topics | Partitions total |
|---|---|---|
| Current (multi-type) | 1 | 5 |
| Proposed (per-type) | 3 (bars, quotes, trades) | 1+5+3 = 9 |

Kafka handles hundreds of topics trivially. 3 extra topics is negligible operational overhead.

---

## 4. What This Means for the Consumer Class

With per-type topics, `DataTopicConsumer` becomes clean and simple:

- **Each topic IS single-type** — no dispatch by `event_type` needed. The `event_type`
  header can still be present (for observability) but the consumer doesn't dispatch on it.
- **Filters are callbacks**: `key_filter`, `header_filter`, `model_filter` — same
  philosophy as `EventRouter.filter_fn`, composable, arbitrary logic.
- **No dedup** — `DedupFilter` stays standalone; `_DataTransport` applies it via
  `model_filter` callback (dedup is a transport-layer concern, not a consumer concern).
- **No payload decode filter** — filtering on decoded model fields is already covered
  by `model_filter`. Filtering on raw payload bytes before parsing would be an
  optimization for very high-throughput topics but adds complexity with unclear benefit.
- **Continuous polling** — `__aiter__` runs forever until cancelled/broken
  (same as `TransportConsumer`, `TypedConsumer`).

### Before/After: `_DataTransport._consume_typed()`

**Before** (20 lines, mixing transport + filter + dedup + parse):
```python
async def _consume_typed[T](self, topic, model_type, group, *, event_id=""):
    consumer = TransportConsumer(topic, self._settings, group)
    try:
        async for msg in consumer:
            if event_id and msg.headers.get(Header.EVENT_ID) != event_id:
                continue
            seq = msg.headers.get(Header.SEQUENCE, "")
            if seq and self._dedup.is_duplicate(
                msg.headers.get(Header.SOURCE, msg.headers.get(Header.SOURCE_APP, "")), seq
            ):
                continue
            try:
                yield model_type.model_validate_json(msg.payload)
            except Exception:
                continue
    finally:
        await consumer.close()
```

**After** (~8 lines, consumer owns parse+filter; dedup via model_filter callback):
```python
async def _consume_typed[T](self, topic, model_type, group, *, event_id=""):
    consumer = DataTopicConsumer(
        topic=topic, settings=self._settings, model_type=model_type,
        group_suffix=group,
        header_filter=lambda h: h.get("event_id") == event_id if event_id else True,
        model_filter=lambda _m, raw: not self._dedup.is_duplicate(
            raw.headers.get(Header.SOURCE, raw.headers.get(Header.SOURCE_APP, "")),
            raw.headers.get(Header.SEQUENCE, ""),
        ),
    )
    async for model, _raw in consumer:
        yield model
```

---

## 5. Class Placement in the SDK

| Class | Layer | Use case | Dispatch | Filtering |
|---|---|---|---|---|
| `TransportConsumer` | L1 | Raw Kafka messages | None | None |
| `TypedConsumer` | L2 | Multi-type event topics | `event_type` header | None |
| **`DataTopicConsumer`** ← NEW | L2 | Per-type data topics | None (topic IS type) | 3 callbacks: key, header, model |
| `EventRouter` | L3 | Handler dispatch on events | `event_type` → handler | `filter_fn` per type |
| `RequestReply` | L3 | Request/response | `event_id` correlation | Inline header match |
| `ReplayConsumer` | L3 | Topic replay | `event_type` (via TypedConsumer) | Sentinel predicate |

**Why Layer 2, not Layer 3**: Like `TypedConsumer`, this class **iterates typed models**.
It doesn't add messaging semantics (handler dispatch, request/response, replay). It's a
typed iterator — same abstraction level as `TypedConsumer`, just for a different topic
pattern.

**No overlap with `EventRouter`**: `EventRouter` dispatches registered types to registered
handlers on event topics. `DataTopicConsumer` yields typed models to the caller on data
topics. They solve different problems in different domains.

---

## 6. API: `DataTopicConsumer[T]`

### Where: `tradingcz.sdk.typed.data_topic_consumer.py`

```python
class DataTopicConsumer[T: BaseModel]:
    """Consume a single Pydantic model type from a Kafka data topic.

    For per-type data topics (e.g. ``{env}-stock-stream-bars`` carries
    only ``Bar`` messages).  Uses ``TransportConsumer`` internally with
    inline JSON parsing.

    Three optional filter callbacks (AND logic, all must pass):
    - ``key_filter``: predicate on the raw Kafka key string
    - ``header_filter``: predicate on the full header dict
    - ``model_filter``: predicate on (parsed model, raw message)
      — same signature as ``EventRouter.filter_fn``

    Continuous polling until cancelled or loop broken.

    Usage::

        consumer = DataTopicConsumer(
            topic="dev-stock-stream-bars",
            settings=kafka_settings,
            model_type=Bar,
            group_suffix="my-strategy",
            key_filter=lambda k: k in ("AAPL", "SPY"),
            header_filter=lambda h: h.get("event_id") == "abc-123",
            model_filter=lambda bar, raw: bar.close > 0,
        )
        async for model, raw in consumer:
            process(model)
            await consumer.commit(raw)
    """

    def __init__(
        self,
        topic: str,
        settings: KafkaSettings,
        model_type: type[T],
        *,
        group_suffix: str,
        # ── Filter callbacks (all optional, AND logic) ──
        key_filter: Callable[[str], bool] | None = None,
        header_filter: Callable[[dict[str, str]], bool] | None = None,
        model_filter: Callable[[T, KafkaMessage], bool] | None = None,
        # ── Standard consumer options ──
        auto_commit: bool = True,
        auto_offset_reset: str | None = None,
        poll_timeout_ms: int | None = None,
        batch_size: int | None = None,
        on_error: Callable[[KafkaMessage], Awaitable[None]] | None = None,
    ) -> None: ...

    async def commit(self, msg: KafkaMessage) -> None: ...
    async def __aiter__(self) -> AsyncIterator[tuple[T, KafkaMessage]]: ...
```

### Key Design Decisions

1. **`TransportConsumer` internally** — no `event_type` dispatch; topic IS the type
2. **`JsonDeserializer` for parsing** — reuse existing, consistent error handling
3. **Yields `(model, raw)` tuples** — caller needs `raw` for `commit()` and header inspection
4. **Three callback filters** — `key_filter`, `header_filter`, `model_filter`; same
   philosophy as `EventRouter.filter_fn`; arbitrary composable logic, not rigid dict matching
5. **NO dedup** — `DedupFilter` remains standalone; applied via `model_filter` callback
6. **Continuous polling** — `__aiter__` runs forever until cancelled/broken; same as all SDK consumers
7. **`on_error` callback** — same pattern as `TypedConsumer`, for unparseable messages

---

## 7. Implementation Sketch (~90 lines)

```python
class DataTopicConsumer[T: BaseModel]:
    def __init__(self, topic, settings, model_type, *, group_suffix,
                 key_filter=None, header_filter=None, model_filter=None,
                 auto_commit=True, auto_offset_reset=None,
                 poll_timeout_ms=None, batch_size=None, on_error=None):
        self._topic = topic
        self._settings = settings
        self._model_type = model_type
        self._group_suffix = group_suffix
        self._key_filter = key_filter
        self._header_filter = header_filter
        self._model_filter = model_filter
        self._auto_commit = auto_commit
        self._auto_offset_reset = auto_offset_reset
        self._poll_timeout_ms = poll_timeout_ms
        self._batch_size = batch_size
        self._on_error = on_error
        self._deserializer = JsonDeserializer()
        self._session: TransportConsumer | None = None

    async def commit(self, msg: KafkaMessage) -> None:
        if self._session is None:
            raise RuntimeError("commit() called outside iteration")
        await self._session.commit(msg)

    async def __aiter__(self) -> AsyncIterator[tuple[T, KafkaMessage]]:
        self._session = TransportConsumer(
            self._topic, self._settings, self._group_suffix,
            auto_offset_reset=self._auto_offset_reset,
            poll_timeout_ms=self._poll_timeout_ms,
            batch_size=self._batch_size,
        )
        async for msg in self._session:
            # ── Filter: key ──
            if self._key_filter is not None and not self._key_filter(msg.key):
                continue
            # ── Filter: headers ──
            if self._header_filter is not None and not self._header_filter(msg.headers):
                continue
            # ── Parse ──
            try:
                model = self._deserializer.deserialize(
                    msg.payload, model_type=self._model_type
                )
            except Exception:
                logger.debug("Skipping unparseable %s on %s",
                             self._model_type.__name__, self._topic, exc_info=True)
                await self._notify_error(msg)
                continue
            # ── Filter: parsed model ──
            if self._model_filter is not None and not self._model_filter(model, msg):
                continue
            # ── Yield ──
            yield model, msg
            if self._auto_commit:
                await self._session.commit(msg)

    async def _notify_error(self, msg: KafkaMessage) -> None:
        if self._on_error is not None:
            try:
                await self._on_error(msg)
            except Exception:
                logger.warning("on_error callback raised for %s", self._topic, exc_info=True)
```

---

## 8. Files to Create/Modify

| File | Action |
|---|---|
| `sdk/tradingcz/sdk/typed/data_topic_consumer.py` | **CREATE** (~90 lines) |
| `sdk/tradingcz/sdk/typed/__init__.py` | Add `DataTopicConsumer` export |
| `sdk/tradingcz/sdk/market_data/_internal/_transport.py` | Refactor `_consume_typed()` to use it |
| `sdk/tests/tradingcz/sdk/typed/test_data_topic_consumer.py` | **CREATE** unit tests |

### Follow-up work (separate task)

| File | Action |
|---|---|
| `sdk/tradingcz/sdk/transport/kafka_topic.py` | Split `market_data` and `historical_data` into per-type topics |
| `ingestion/tradingcz/ingestion/handlers/stock_stream.py` | Publish to per-type topics instead of one shared topic |
| `ingestion/tradingcz/ingestion/handlers/stock_historical.py` | Publish to per-type topics; fix hardcoded `EventType.BAR` |

---

## 9. Risk Assessment

| Factor | Assessment |
|---|---|
| **Scope** | Small (~90 line class + 1 internal refactor) |
| **Testability** | Testable in isolation with `MockConsumer` |
| **Call sites** | Only 1 internal call site (`_consume_typed`); all others unchanged |
| **Backward compat** | No public API changes; `_consume_typed` is internal (`_internal`) |
| **Overlap with EventRouter** | None — different domains (data topics vs event topics), different patterns (yield vs handler dispatch) |
| **Overlap with TypedConsumer** | None — TypedConsumer dispatches by `event_type` for multi-type topics; this does single-type inline parse for per-type topics |
| **Future use** | Any service consuming data topics directly (testing tools, monitoring, future strategies) |

---

## 10. Recommendation

**Implement `DataTopicConsumer`** — a focused, single-concern class for consuming
per-type data topics:

1. **Callback filters**: `key_filter`, `header_filter`, `model_filter` — same philosophy as `EventRouter.filter_fn`
2. **No dedup**: `DedupFilter` remains standalone; applied via `model_filter` callback
3. **Continuous polling**: `__aiter__` runs forever until cancelled (consistent with all SDK consumers)
4. **Small and testable**: ~90 lines, one internal refactor, zero public API changes

**Prerequisite**: Split data topics into per-type topics (separate task). The consumer
class design assumes per-type topics where each topic carries exactly one model type.
This prerequisite is justified independently by volume isolation, independent topic
configuration, and broker-agnostic design.
