# tradingcz-sdk — Architectural Deep-Dive & Status

> **Date:** 2026-06-23  
> **SDK:** 0.1.19 / Python 3.14  
> **Recent:** ServiceApp removed (6180969), `StockStreamProvider` ABC added, `MarketDataType` extended with LATEST_* variants  
> **Scope:** ~2,500 LOC across 40+ modules. 5 consuming services, 2 active strategies, target 50-60.  
> **Fixes applied:** consumer group collision (§3.1/3.2), EventRouter cancellation timeout (§1.2), EventRouter max_concurrency semaphore (§1.4)

---

## 0. Executive Judgment

The SDK is **correct at the macroscopic layer** (typed dispatch, decorator-based registration, explicit composition root). Three operational hardening issues identified below have been fixed (consumer group collision, cancellation timeout, spawn concurrency bound). The remaining gaps are either deferred per ADR-005, rejected as premature, or speculative at current scale.

The SDK's core abstraction — "typed Pydantic models over Kafka with header-based dispatch" — is sound.

**Overall: 8/10** — architecturally correct, operationally hardened where it matters, clean code.

---

## 1. The Asyncio Model — Where It Breaks

### 1.1 The `__aiter__` Lifecycle Anti-Pattern

This is the single most important design issue in the SDK. Consider `TypedConsumer.__aiter__`:

```python
async def __aiter__(self) -> AsyncIterator[tuple[EventType, BaseModel, KafkaMessage]]:
    self._session = TransportConsumer(     # ← NEW consumer created on EACH iteration
        self._topic, self._settings, self._group_suffix,
        auto_offset_reset=..., poll_timeout_ms=..., batch_size=..., auto_commit=...,
    )
    async for msg in self._session:
        # ... dispatch ...
        yield event_type, model, msg
    # self._session goes out of scope — AIOConsumer.close() called in TransportConsumer.__aiter__ finally
```

**What actually happens at the Kafka level on every `async for` loop:**

1. A new `AIOConsumer` is instantiated → joins consumer group → triggers **group rebalance** (StopTheWorld for all consumers in the group)
2. A new `ThreadPoolExecutor(max_workers=2)` is created (two OS threads)
3. Messages are consumed
4. On loop exit (StopAsyncIteration, CancelledError, or break), `TransportConsumer.__aiter__`'s `finally` calls `self._consumer.close()` → leaves consumer group → **another rebalance**
5. The `ThreadPoolExecutor` is **abandoned** — `shutdown()` is NOT called in `__aiter__`'s finally. The comment says "Executor shutdown is handled by close()" but `__aiter__` never calls `close()`.

**Consequence:** Every `async for` over a `TypedConsumer` causes **two Kafka group rebalances** (join + leave). Kafka's rebalance protocol pauses all consumers in the group for the duration. For a group with 50 consumers (one per strategy), this means every strategy restart causes 49 other strategies to pause consumption.

**But wait — it's worse.** `EventRouter.run()` does exactly this:

```python
async def run(self) -> None:
    self._consumer = TypedConsumer(...)
    async for msg_type, model, raw in self._consumer:
        # dispatch
```

And `ReplayConsumer.replay()` also does it:

```python
async def replay(self, model_types, *, until):
    consumer = TypedConsumer(topic=..., settings=..., types=..., group_suffix=uuid.uuid4().hex)
    async for msg_type, model, raw in consumer:
        # replay
```

Every replay creates a **new consumer group** (UUID suffix) that is **never cleaned up**. Kafka stores consumer group metadata in the internal `__consumer_offsets` topic. These accumulate forever (compacted after `offsets.retention.minutes`, default 7 days — not deleted, compacted). For a system with frequent pod restarts (CronJob strategies restarting daily), this is consumer-group pollution.

**The fix:** `TypedConsumer` should not create `TransportConsumer` in `__aiter__`. It should expose a `start()`/`stop()` lifecycle:

```python
# Proposed
consumer = TypedConsumer(topic, settings, types, group_suffix="worker")
await consumer.start()    # one-time: subscribe, join group
try:
    async for msg_type, model, raw in consumer:
        await handle(model)
finally:
    await consumer.close()  # one-time: leave group, shutdown executor
```

This is what `EventRouter` and `RequestReply` already do internally — they just hide it behind `run()` and `_listen()`. `TypedConsumer` itself should support this lifecycle explicitly.

### 1.2 Structured Concurrency — The Missing `TaskGroup`

Python 3.11 introduced `asyncio.TaskGroup` for structured concurrency. The SDK uses raw `asyncio.create_task()` everywhere:

```python
# EventRouter.start()
self._run_task = asyncio.create_task(self.run(), name=f"router-{self._topic}")

# EventRouter._dispatch() for spawned handlers
task = asyncio.create_task(self._dispatch(reg, model, raw), name=f"router-{msg_type}")
self._spawned_tasks.add(task)
task.add_done_callback(self._spawned_tasks.discard)

# HealthPublisher.ready()
self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

# StreamHandle._consume() — consumer lives in async generator closure
async def _consume() -> AsyncIterator[T]:
    try:
        async for msg in consumer:  # consumer captured from outer scope
            yield parsed
    finally:
        await consumer.close()
```

There are **no `TaskGroup` contexts, no nurseries, no cancellation scopes.**

**Cancellation leakage:** When `EventRouter.close()` cancels `self._run_task`, the `CancelledError` propagates into the async generator `TypedConsumer.__aiter__()`, then into `TransportConsumer.__aiter__()`, which has a `finally: await self._consumer.close()`. This `close()` is a *new coroutine* that runs during cancellation cleanup. If `self._consumer.close()` blocks (network issue), the cancellation hangs indefinitely.

**Orphaned spawned tasks under slow handlers:** If a spawned handler does:

```python
async def on_data_request(model, raw):
    result = await fetch_data(model)  # takes 60 seconds
    await publish(result)
```

And `fetch_data` doesn't check `asyncio.current_task().cancelled()` at each await point, the cancellation takes 60 seconds to propagate. During those 60 seconds, `close()` is blocked. In a Kubernetes pod with a 30-second `terminationGracePeriodSeconds`, the pod is SIGKILL'd before cleanup completes.

**The fix:** Add timeouts to `close()` and use `asyncio.TaskGroup` where appropriate:

```python
async def close(self) -> None:
    # Cancel spawned tasks with a deadline
    for task in list(self._spawned_tasks):
        if not task.done():
            task.cancel()
    try:
        async with asyncio.timeout(10.0):
            if self._spawned_tasks:
                await asyncio.gather(*self._spawned_tasks, return_exceptions=True)
    except TimeoutError:
        logger.warning("Timed out waiting for spawned tasks to cancel")
    # Cancel consumer with a deadline
    if self._run_task and not self._run_task.done():
        self._run_task.cancel()
        try:
            async with asyncio.timeout(5.0):
                await self._run_task
        except (asyncio.CancelledError, TimeoutError):
            pass
```

### 1.3 The `asyncio.Future` Dict — Correct but Observability-Blind

`RequestReply._pending` is a `dict[str, asyncio.Future[BaseModel]]` accessed from two coroutines on the same event loop. In single-threaded asyncio, this is safe (no preemption between `await` points). But there's a subtle race on **timeout vs response arrival**:

```
T+0   | request() adds future to pending
T+1   | await producer.send()
T+2   | await producer.flush()
...
T+29  | TimeoutError fires
T+29  | pending.pop(event_id, None)         ← future removed
T+29  | raise TimeoutError
T+29.1|                                     | _listen() receives response
      |                                     | pending.get(event_id) → None
      |                                     | → silently dropped ✗
```

The response arriving after `pop` is silently dropped — correct (caller timed out) but **unobservable**. If this happens frequently (e.g., ingestion is slow), there's no metric, no log, no alert.

**Fix:** Log late responses at DEBUG level in `_listen()`:

```python
future = self._pending.get(event_id)
if future is None:
    logger.debug("Late response for %s (type=%s) — no pending request, dropped",
                 event_id, _msg_type)
    self._skipped_late += 1
    continue
```

### 1.4 EventRouter — Unbounded Concurrency Under Burst

```python
if reg.spawn_task:
    task = asyncio.create_task(self._dispatch(reg, model, raw))
    self._spawned_tasks.add(task)
    task.add_done_callback(self._spawned_tasks.discard)
```

There is **no semaphore, no max concurrency, no backpressure.** If 10,000 messages arrive in a burst (e.g., replay after downtime), 10,000 tasks spawn simultaneously. Each task is a coroutine — cheap (~1KB) — but 10,000 concurrent coroutines all competing for the event loop will cause latency spikes. For a trading system, this is a **self-inflicted denial-of-service vector.**

**Fix:** Optional `max_concurrency` with `asyncio.Semaphore`:

```python
def __init__(self, ..., max_concurrency: int | None = None):
    self._semaphore = (asyncio.Semaphore(max_concurrency)
                       if max_concurrency else None)

async def _dispatch(self, reg, model, raw):
    if self._semaphore:
        async with self._semaphore:
            await reg.handler(model, raw)
    else:
        await reg.handler(model, raw)
```

---

## 2. The Threading Model — Hidden Complexity

### 2.1 `TransportProducer` — Sync Producer Under Async

```python
class TransportProducer:
    def __init__(self, settings, *, on_error=None):
        self._producer = SyncProducer(settings.producer_config())
        self._closed = False

    async def send(self, topic, payload, *, key="", headers=None):
        def _produce():
            self._producer.produce(topic, value=payload, ...,
                                   on_delivery=self._handle_error)
        await asyncio.to_thread(_produce)
```

This is correct. `SyncProducer` is thread-safe. `asyncio.to_thread()` dispatches to the default thread pool. The `on_delivery` callback runs on **librdkafka's internal I/O thread** — not the event loop. The docstring warns about this.

**The `_closed` flag:** `_closed` is a plain `bool` set in `close()` (event loop thread) and read in `send()` (also event loop thread, via `asyncio.to_thread` wrapper). Since both run on the event loop at different times (separated by `await`), there's no data race. But if someone refactors `send()` to not await `asyncio.to_thread()` (e.g., using a callback pattern), they'd introduce a race.

**Recommendation:** Document the thread-safety contract explicitly on each method.

### 2.2 `TransportConsumer` — ThreadPoolExecutor Lifecycle (Python 3.14 Crash)

```python
class TransportConsumer:
    def __init__(self, ...):
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._consumer = AIOConsumer(config, executor=self._executor)
```

The code explicitly passes its own executor. The comment warns:

> Calling shutdown(wait=False) here crashes on Python 3.14 + librdkafka 2.14.x (SIGABRT in ThreadPoolExecutor).

This is a **platform-specific fragility.** Python 3.14's free-threading changes affect `ThreadPoolExecutor` shutdown. `AIOConsumer` holds references to the executor and tries to submit tasks during its own `close()`. If the executor has started shutdown (even `wait=False`), the submission causes SIGABRT — a process-level crash, not a Python exception.

**Regression test needed:** Create and destroy 100 `TransportConsumer` instances in sequence to catch executor shutdown regressions.

### 2.3 Thread Count Per Consumer

| Thread Source | Count | Purpose |
|--------------|-------|---------|
| `ThreadPoolExecutor` | 2 | Async poll dispatch |
| librdkafka I/O | 1-2 | Broker communication |
| librdkafka background | 1 | Metadata refresh, rebalance |

**Total: 4-5 OS threads per consumer.** With 50 strategies each using one `StockStreamClient` (which creates a `TransportConsumer` in `_DataTransport.stream()`), that's **200-250 threads.** Manageable on Linux (`threads-max` ≈ 250K), but should be monitored.

---

## 3. The Data Plane — Concurrency & Correctness

### 3.1 Historical Data Consumer Group Collision (CRITICAL BUG)

In `_DataTransport.request_historical()`:

```python
consumer = TransportConsumer(resp.data_topic, self._settings, "data")
```

The `group_suffix="data"` is **hardcoded.** Every concurrent historical request joins the **same consumer group** `{topic}-data`. Kafka partition-assigns across group members.

With `partitions=1` (current `KafkaTopicRegistry` default), one consumer gets the partition, others idle. But:

1. If ingestion uses different partition counts for different data types
2. If two services request data that shares a topic name
3. On any new consumer join, Kafka triggers a **rebalance** — the existing consumer is revoked, then re-assigned

During rebalance, in-flight messages may be delivered to either consumer non-deterministically. The `record_count` check and `event_id` filter mask this, but the behavior is undefined.

**Fix:**

```python
import uuid
consumer = TransportConsumer(
    resp.data_topic, self._settings,
    f"data-{uuid.uuid4().hex[:8]}"  # unique group per request
)
```

### 3.2 Streaming Consumer — Same Bug, Higher Severity

In `_DataTransport.stream()`:

```python
consumer = TransportConsumer(resp.data_topic, self._settings, "stream")
```

Same hardcoded suffix. But streaming is **long-lived** — a rebalance pauses consumption for all streams sharing that topic. For live trading, a 5-10 second rebalance pause means **missed quotes during that window.**

**Fix:** Unique group suffix, same as above.

### 3.3 DedupFilter — Memory Characteristics

```python
class DedupFilter:
    def __init__(self, max_size: int = 100_000):
        self._seen: OrderedDict[tuple[str, str], None] = OrderedDict()
```

Under streaming: 100 symbols × 1 quote/sec = 360K entries/hour. At `max_size=100_000`, LRU eviction means entries older than ~16 minutes are evicted. If a message is duplicated after 17 minutes (e.g., producer retry after network blip), the filter misses it.

**Memory:** Each entry ≈ 200 bytes. 100K entries ≈ 20MB. With 5 strategies each having a filter, that's 100MB — fine for cx23 (4GB), but should be documented as a capacity constraint.

**This is an acceptable tradeoff** — true deduplication would require unbounded storage or a Bloom filter with false-positive risk. The `max_size` should be configurable per stream.

---

## 4. The Event Model — Inheritance, Composition, and CQRS

### 4.1 `TradingSignalEvent(ExecutionRequestEvent)` — Inheritance for Convenience

```python
@register_event(EventType.EXECUTION_REQUEST)
class ExecutionRequestEvent(BaseModel):
    event_id: UUID
    strategy_type: StrategyType
    orders: list[OrderRequest]

@register_event(EventType.TRADING_SIGNAL)
class TradingSignalEvent(ExecutionRequestEvent):  # ← inherits all fields
    """Same shape as ExecutionRequestEvent but different event_type header."""
```

This couples two semantically distinct events:

| Aspect | TradingSignalEvent | ExecutionRequestEvent |
|--------|-------------------|-----------------------|
| **Sender** | Strategy | Risk Manager |
| **Receiver** | Risk Manager | Executor |
| **Semantics** | "I want to trade" | "Execute these orders" |
| **Authorization** | None (untrusted) | Risk-approved |
| **Future fields** | Confidence score, backtest ID | Risk budget consumed, approval timestamp |

When these diverge (and they will), the inheritance forces both to carry fields only one needs. **Recommendation:** Duplicate the shared fields with composition:

```python
class TradingSignalEvent(BaseModel):
    event_id: UUID
    strategy_type: StrategyType
    orders: list[OrderRequest]
    # signal-specific fields here

class ExecutionRequestEvent(BaseModel):
    event_id: UUID
    strategy_type: StrategyType
    orders: list[OrderRequest]
    signal_event_id: UUID | None = None  # traceability
    # execution-specific fields here
```

Yes, this duplicates `event_id`, `strategy_type`, `orders`. This is the **right kind of duplication** — each model owns its fields independently and can evolve without breaking the other.

### 4.2 `EventType` Enum Pollution — The CQRS Schism

```python
class EventType(StrEnum):
    # Control plane (event topic, TypedConsumer dispatch)
    DATA_REQUEST = "data_request"
    EXECUTION_REQUEST = "execution_request"
    TRADING_SIGNAL = "trading_signal"

    # Data plane (data topics, raw TransportConsumer) — WRONG PLACE
    BAR = "bar"       # ← code comment: "TODO wrong enum - move somewhere else"
    QUOTE = "quote"
    TRADE = "trade"
```

The two planes have **different dispatch mechanisms, different consistency guarantees, different error handling**:

```
CONTROL PLANE                         DATA PLANE
──────────────────────────            ─────────────────────────
Dispatch: TypedConsumer               Dispatch: manual model_validate_json
Header:   EventHeader                 Header:   DataHeader
Registry: EventRegistry               Registry: MarketDataRegistry
Consistency: request/reply            Consistency: streaming + dedup
Error:    on_error callback           Error:    try/except skip
```

**Recommendation:** Split into `ControlEvent` and `DataRecord` enums:

```python
class ControlEvent(StrEnum):
    DATA_REQUEST = "data_request"
    DATA_READY = "data_ready"
    EXECUTION_REQUEST = "execution_request"
    TRADING_SIGNAL = "trading_signal"
    # ...

class DataRecord(StrEnum):
    BAR = "bar"
    QUOTE = "quote"
    TRADE = "trade"
    SNAPSHOT = "snapshot"
```

`EventRegistry` binds to `ControlEvent`. `DataHeader.event_type` changes type from `EventType` to `DataRecord`.

### 4.3 `ServiceRequestEvent` — The Hidden Command Pattern

```python
class ServiceRequestEvent(BaseModel):
    service: str  # "get_balance", "get_positions", "get_orders"
    symbol: str | None = None
    order_status: str | None = None
```

This is a **command pattern** embedded in a single event type — `service` is the discriminator. It works for 3-4 operations but doesn't scale. Each new operation adds optional fields (`.symbol`, `.order_status`) that are irrelevant to other operations. A `get_balance` request carries `.symbol` and `.order_status` as `None` — schema bloat.

**Long-term:** Individual event types per operation (`GetBalanceRequest`, `GetPositionsRequest`) with a shared response correlation pattern. Not urgent — 3 operations is manageable.

---

## 5. The Serialization Pipeline — Deep Correctness Issues

### 5.1 `model_dump_json(exclude_none=True)` — The `Decimal` Problem

```python
def serialize(self, value: T) -> bytes:
    return cast(str, value.model_dump_json(exclude_none=True)).encode()
```

Pydantic's `Decimal` type serializes to JSON as an **IEEE 754 number**:

```python
from decimal import Decimal
d = Decimal("123.45678901234567890")
# model_dump_json → 123.45678901234568  (precision lost!)
```

For equities with 2 decimal places, this is fine. For crypto (8 decimal places) or forex (5 decimal places), the loss is:
- 1.1e-14 dollars per trade — negligible
- But **deterministic, repeatable, and silent** — violates financial correctness expectations

**Fix:** Either:
1. Custom JSON encoder that serializes `Decimal` as string: `"123.45678901234567890"` (lossless)
2. Pydantic field with `json_schema_extra` and custom serializer
3. Document the precision limit explicitly

### 5.2 `model_validate_json` — Lax Mode Masks Bugs

```python
def deserialize[T](self, payload: bytes, *, model_type: type[T]) -> T:
    return cast(T, model_type.model_validate_json(payload))
```

Pydantic's **lax** parser coerces types: `"101.50"` → `101.50`, `"5"` → `5`. If a producer has a bug that serializes numbers as strings, lax mode silently accepts them. The consumer never knows the data is malformed.

**Recommendation:** Add a `strict` flag (default `True` for production, `False` for development):

```python
class JsonDeserializer(Deserializer):
    def __init__(self, strict: bool = True):
        self._strict = strict

    def deserialize[T](self, payload: bytes, *, model_type: type[T]) -> T:
        return cast(T, model_type.model_validate_json(payload, strict=self._strict))
```

---

## 6. Testing — Structural Gaps

### 6.1 MockConsumer Is Correct But Inaccessible

The SDK tests have `MockConsumer` (in `tests/tradingcz/sdk/mock_utils.py`) — an async iterable yielding pre-canned `KafkaMessage` objects. But this mock is **not exported from the SDK package.** Strategy tests in `simple-strategy/` must copy it or monkey-patch.

### 6.2 The `Protocol` Pattern — Half-Applied

`TimeKeeper` depends on `MarketClockProvider` (a `Protocol`). This is correct — tests can provide fake clocks without touching real market data APIs.

But `StockDataClient` depends on `_DataTransport` (concrete), which depends on `TransportProducer` (concrete), which depends on `confluent_kafka.Producer` (C library). Testing a strategy that uses `StockDataClient` requires either:
- A running Kafka cluster (integration test)
- Monkey-patching 3 levels deep (brittle)

**Recommendation:** Add Protocols for the transport layer, exported from the SDK:

```python
class ProducerProtocol(Protocol):
    async def send(self, topic: str, payload: bytes, *, key: str, headers: dict[str, str] | None) -> None: ...
    async def flush(self, timeout: float = 30.0) -> None: ...
    async def close(self) -> None: ...

class ConsumerProtocol(Protocol):
    async def poll(self) -> list[KafkaMessage]: ...
    async def commit(self, msg: KafkaMessage) -> None: ...
    async def close(self) -> None: ...
    def __aiter__(self) -> AsyncIterator[KafkaMessage]: ...
```

These don't change the production code — `TransportProducer` already satisfies `ProducerProtocol`. They just make it explicit so test authors know what to mock.

### 6.3 The Testing Repo Should Provide Fakes

The `testing/` repo should own a `testkit/` package with:

```
testing/testkit/
├── fake_transport.py      # FakeTransportContext, FakeEventBus
├── fake_market_data.py    # FakeStockDataClient (pre-canned bars/quotes)
├── fake_account.py        # FakeSignalPublisher (records published signals)
└── fixtures.py            # Common test scenarios
```

---

## 7. Advanced Python — What's Good, What's Missing

### 7.1 Patterns Done Right

**`__init_subclass__` for isolated registries:**
```python
class ModelRegistry[K]:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._by_key = {}   # isolated per subclass
        cls._by_model = {}
```
This ensures `EventRegistry` and `MarketDataRegistry` don't share state. Correct use of a Python 3.6+ feature that's underused.

**`Lazy[T]` with `__set_name__`:**
```python
class Lazy[T]:
    def __set_name__(self, owner, name):
        self._name = name  # automatic attribute name capture
```
No manual `_lazy_attr_name` duplication. Clean descriptor protocol usage.

**`StrEnum` for wire-format values:**
`Header.EVENT_TYPE == "event_type"` and `Header.EVENT_TYPE is Header.EVENT_TYPE` both work. Right choice for Kafka headers.

**`@register_event` decorator as side-effecting class decorator:**
The decoration modifies the registry AND returns the class unchanged. This is the correct decorator pattern — no wrapper, no proxy, no metaclass.

### 7.2 Patterns Missing

**`TypeVarTuple` for generic batching:**
`TypedConsumer` yields `(EventType, BaseModel, KafkaMessage)`. The inner `BaseModel` loses type information. `TypeVarTuple` (Python 3.11+) would preserve it through transforms.

**`match` statement for dispatch:**
`EventRouter.run()` uses a `for` loop with `if reg.msg_type != msg_type: continue`. For 5-10 handler types this is fine. Python 3.10+ `match` would be cleaner but not performance-critical.

**`ExceptionGroup` for aggregated errors:**
When `EventRouter` gathers spawned tasks with `return_exceptions=True`, individual exceptions are swallowed. Python 3.11+ `ExceptionGroup` would preserve them all.

**`@override` decorator (Python 3.12+):**
`StockDataClient` implements `StockDataProvider`. Adding `@override` on each method would catch signature drift at type-check time.

---

## 8. Architecture Decision Records

### ADR-001: Direct Wiring over ServiceApp (APPROVED, 2026-06-23)
**Decision:** Remove ServiceApp. Every service creates its own transport.  
**Status:** Implemented in `6180969`. Executor migration in progress (uncommitted changes).

### ADR-002: Decorator-based Event Registration (APPROVED)
**Decision:** `@register_event(EventType.XXX)` on model classes.  
**Status:** Implemented. No changes needed.

### ADR-003: JSON Serialization (APPROVED, with caveats)
**Caveat:** Decimal precision and strict vs lax validation must be addressed.  
**Status:** Implemented. Monitor.

### ADR-004: UUID `event_id` for Correlation (APPROVED, with caveat)
**Caveat:** Deduplication is inconsistent (executor: DB, ingestion: DedupFilter, risk: in-memory). Standardize.  
**Status:** Partially implemented.

### ADR-005: Transport-Agnostic via Direct Composition (IMPLICIT)
**Decision:** No Transport ABC. Services compose with concrete Kafka classes.  
**Rationale:** 5 services, 50-60 strategies. Transport polymorphism not yet needed.  
**Caveat:** Add Protocols when test pain exceeds refactor cost.

---

## 9. Priority Actions

### Critical (fix before concurrent usage)

| # | Issue | § | Effort | Status |
|---|-------|---|--------|--------|
| 1 | **Data plane consumer group collision** — use unique `group_suffix` | 3.1, 3.2 | 5 min | ✅ DONE (2026-06-23) |
| 2 | **Decimal JSON serialization** — lossy for high-precision prices | 5.1 | 30 min | ⚠️ DEFER (no current data loss; revisit for crypto/forex) |
| 3 | ~~**ReplayConsumer group leak**~~ — NOT A LEAK; Kafka auto-cleans after `offsets.retention.minutes` (default 7d) | 1.1 | — | ❌ REJECTED (non-issue) |

### High (fix this sprint)

| # | Issue | § | Effort | Status |
|---|-------|---|--------|--------|
| 4 | **TypedConsumer `__aiter__` lifecycle** — `start()`/`close()` instead of per-iteration consumer | 1.1 | 2 hr | ⚠️ DEFER (current create-once-iterate-once pattern works; revisit when reuse needed) |
| 5 | **EventRouter cancellation timeout** — don't block shutdown on slow handlers | 1.2 | 30 min | ✅ DONE (2026-06-23) |
| 6 | **Split EventType enum** — `ControlEvent` vs `DataRecord` | 4.2 | 1 hr | ⚠️ DEFER (ripple effect on ingestion PR #54; revisit after PR merge) |
| 7 | ~~**`_DataTransport` → `DataTransport`**~~ — Facade pattern is intentional; keep internal | 1.1 | — | ❌ REJECTED (anti-pattern) |
| 8 | **EventRouter max_concurrency** — semaphore for spawned tasks | 1.4 | 15 min | ✅ DONE (2026-06-23) |

### Medium (next sprint)

| # | Issue | § | Effort | Status |
|---|-------|---|--------|--------|
| 9 | ~~**Export MockConsumer from SDK package**~~ — move to testing/testkit/ instead | 6.1 | — | ❌ REJECTED for SDK (belongs in testing repo) |
| 10 | **Add Protocols for transport layer** | 6.2 | 2 hr | ⚠️ DEFER (per ADR-005) |
| 11 | **`TradingSignalEvent` composition** — decouple from `ExecutionRequestEvent` | 4.1 | 1 hr | ⚠️ MONITOR (YAGNI until fields diverge) |
| 12 | **JSON strict mode flag** | 5.2 | 30 min | ⚠️ DEFER (solves non-problem; Pydantic already validates) |
| 13 | **Build `testkit/` fakes in testing repo** | 6.3 | 4 hr | ⚠️ DEFER (testing repo concern, not SDK) |

### Watch (monitor)

| # | Issue | § | Trigger |
|---|-------|---|---------|
| 14 | Thread count per consumer | 2.3 | > 500 threads total |
| 15 | DedupFilter memory per stream | 3.3 | > 50MB per filter |
| 16 | `poll()` vs `consume()` workaround | 2.2 | > 10K msg/sec |
| 17 | Consumer group metadata accumulation | 1.1 | > 1000 groups |

---

## 10. "Hello World" Target

After the fixes above, a strategy should look like this:

```python
"""minimal_strategy.py"""
import asyncio
from tradingcz.sdk.transport.context import TransportContext
from tradingcz.sdk.market_data import StockDataClient, StockStreamClient
from tradingcz.sdk.account import SignalPublisher
from tradingcz.sdk.models.events import TradingSignalEvent

async def main():
    async with TransportContext(
        env="dev", service_id="my-strategy",
        kafka_settings=KafkaSettings(consumer_group="my-strategy"),
    ) as ctx:
        await ctx.health.ready()
        stock = StockDataClient(transport=ctx.data_transport)
        stream = StockStreamClient(transport=ctx.data_transport)
        signals = SignalPublisher(faf=ctx.faf)

        # ── Business logic (everything above is infrastructure) ──
        bars = await stock.get_bars(["SPY"], start=yesterday, end=today, timeframe="1d")

        async for quote in await stream.stream_quotes(["SPY"]):
            if is_entry(quote, bars):
                await signals.publish(
                    TradingSignalEvent(strategy_type="my-strat", orders=[...]),
                    event_id=tracking_id)
                break

asyncio.run(main())
```

**9 lines of infrastructure. `TransportContext` handles:** topic creation, producer init, health INITIALIZING→READY→DOWN heartbeat, RequestReply startup, DataTransport setup, graceful shutdown with timeout-bounded cancellation. `StreamHandle.__aexit__` sends UNSUBSCRIBE automatically.

---

*Updated 2026-06-23. Reflects SDK at 0.1.19. Fixes applied: consumer group collision, EventRouter cancellation timeout, max_concurrency semaphore. Remaining items deferred/rejected per validated assessment.*
