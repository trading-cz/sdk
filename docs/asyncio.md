# Asyncio Best Practices — Trading System (Python 3.14+)

> **Scope**: SDK + downstream repos (ingestion, executor, simple-strategy, risk, testing)  
> **Python target**: `>=3.14` — all features from 3.9–3.14 available  
> **Environment**: k3s pods, Kafka messaging, strategy execution, market data streaming

---

## 1. Philosophy

**Rule of thumb**: Use asyncio features that reduce code, improve clarity, or fix
correctness bugs. Do NOT use features just because they exist. If a simpler
synchronous approach works equally well (e.g., `queue.Queue.get_nowait()` vs
`asyncio.Queue` for non-async contexts), prefer the simpler one.

### Decision hierarchy
```
1. Does this need to be async at all?
   ├─ I/O (Kafka, HTTP, DB, WebSocket) → YES
   └─ CPU-bound or in-memory only → NO (use thread executor or keep sync)

2. If async, which primitive?
   ├─ Single awaitable with timeout → asyncio.timeout()
   ├─ Multiple awaitables (race) → asyncio.wait(FIRST_COMPLETED)
   ├─ Multiple awaitables (all) → asyncio.gather()
   ├─ Background work in thread pool → asyncio.to_thread()
   └─ Cross-thread callback → asyncio.run_coroutine_threadsafe()
```

---

## 2. Core Rules (Must Follow)

### 2.1 Never use `asyncio.ensure_future()` from a non-event-loop thread 🔴

`asyncio.ensure_future()` is **not thread-safe**. It must only be called from the
event loop thread. If you're in a callback from a foreign thread (e.g.,
librdkafka delivery callback, WebSocket on_message, etc.), use one of:

| Context | API |
|---------|-----|
| Foreign thread → event loop | `asyncio.run_coroutine_threadsafe(coro, loop)` |
| Event loop → foreign thread | `await asyncio.to_thread(fn)` |
| Foreign thread (fire-and-forget) | `queue.Queue.put()` — let the event loop drain |

**Our approach**: The SDK already removed all `ensure_future()` from foreign-thread
callbacks. `TransportProducer._handle_error` uses `queue.Queue.put()` only.

### 2.2 Prefer `asyncio.to_thread()` over `loop.run_in_executor(None, ...)` 🟡

`asyncio.to_thread()` (3.9+) is the **high-level, recommended API**. Same
behavior, cleaner code.

```python
# ❌ Old
loop = asyncio.get_running_loop()
result = await loop.run_in_executor(None, lambda: client.sync_call())

# ✅ New
result = await asyncio.to_thread(client.sync_call)
```

**Status**: SDK ✅ done. Executor ✅ done. **Ingestion ❌ NOT done** — 11 instances
of `loop.run_in_executor(None, lambda: ...)` in the Alpaca adapters. See §5.1.

### 2.3 Prefer `asyncio.timeout()` over `asyncio.wait_for()` for single awaitables 🟡

`asyncio.timeout()` (3.11+) is the structured concurrency approach. It's more
readable and automatically handles cancellation cleanup.

```python
# ❌ Verbose
try:
    result = await asyncio.wait_for(something(), timeout=10)
except TimeoutError:
    ...

# ✅ Structured
try:
    async with asyncio.timeout(10):
        result = await something()
except TimeoutError:
    ...
```

**Exception**: `asyncio.wait_for()` is still fine when the timeout is a simple
one-liner and the awaitable is an expression (not a block).

```python
# ✅ wait_for is still acceptable here
item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
```

### 2.4 Use `asyncio.wait()` ONLY for multiple-future races 🟢

`asyncio.wait()` is designed for waiting on **multiple** futures simultaneously.
For a single future, use `await future` directly (or with `asyncio.timeout()`).

```python
# ✅ Correct — waiting for FIRST_COMPLETED among 3 tasks
done, pending = await asyncio.wait(
    [order_task, price_task, close_task],
    return_when=asyncio.FIRST_COMPLETED,
)
winner = done.pop()

# ❌ Wrong — single future, use direct await
done, _ = await asyncio.wait([future], timeout=...)
```

**Status**: SDK ✅ done (`request_reply.py` uses `asyncio.timeout()`). Executor
✅ correct (uses `asyncio.wait()` only for multi-future races).

### 2.5 Bound all concurrency — backpressure first 🔴

Never spawn unbounded work. Always cap concurrency with one of:

| Mechanism | When to use |
|-----------|------------|
| `asyncio.Semaphore` | Limit concurrent API calls, DB queries |
| `asyncio.Queue(maxsize=N)` | Worker pool feeding from a bounded queue |
| Fixed-size task set | Known number of parallel operations |

```python
# ✅ Bounded worker pool
queue: asyncio.Queue[Work] = asyncio.Queue(maxsize=100)
workers = [asyncio.create_task(_worker(queue)) for _ in range(5)]

# ❌ Unbounded fan-out — memory risk under load
results = await asyncio.gather(*(process(r) for r in huge_list))
```

**Why**: In trading, market data spikes can produce thousands of messages per
second. Unbounded fan-out causes memory exhaustion and cascading failures.
Bounded queues provide natural backpressure.

### 2.6 Shutdown must be idempotent 🔴

Shutdown paths must be safe to call multiple times. Always drain before close:

1. **Cancel** background tasks
2. **Drain** pending work (flush producers, await cancelled tasks)
3. **Close** transports and connections

```python
# ✅ Idempotent — safe to call twice
async def close(self) -> None:
    if self._closed:
        return
    self._closed = True
    await self._producer.flush()
    # ... close connections ...
```

**Our pattern**: `ServiceApp.close()` is already idempotent. All transport
producers/consumers guard against double-close.

### 2.7 Always handle `asyncio.CancelledError` in background tasks 🔴

Every task spawned with `asyncio.create_task()` must handle `CancelledError` or be
cancelled gracefully during shutdown.

```python
async def _loop() -> None:
    try:
        while True:
            await do_work()
    except asyncio.CancelledError:
        logger.info("Loop cancelled")
        # Optional: cleanup
```

**Our pattern** (from executor/ingestion): All background loops have
`except asyncio.CancelledError` at the top level. All shutdown sequences cancel
tasks, then `await` them to ensure cleanup completes.

### 2.8 `asyncio.gather()` with `return_exceptions=True` for cleanup 🟡

When cancelling multiple tasks during shutdown, use `asyncio.gather()` with
`return_exceptions=True` to avoid one failed cancellation blocking others.

```python
# ✅ Safe cancellation of multiple tasks
for task in pending:
    task.cancel()
await asyncio.gather(*pending, return_exceptions=True)
```

**Status**: Both ingestion and executor already do this correctly.

### 2.9 Named tasks for debugging 🟢

Always pass `name=` to `asyncio.create_task()` for observability. Python 3.14's
`python -m asyncio ps PID` and `pstree PID` display task names.

```python
# ✅ Named tasks are visible in task tree
task = asyncio.create_task(_loop(), name="event_router")
```

**Status**: Executor ✅ uses named tasks. Ingestion ⚠️ does not name tasks.

---

## 3. Our Patterns (Documented Usage)

### 3.1 Background Loop with Shutdown Event

**Where**: `ingestion/service.py`, `executor/adapters/market_data/`

```python
async def _loop(self) -> None:
    try:
        while True:
            for msg in await self.poll():
                yield msg
    except asyncio.CancelledError:
        ...

async def serve(self) -> None:
    router_task = asyncio.create_task(self._loop())
    await self._shutdown.wait()
    router_task.cancel()
    await router_task  # ensures cleanup
```

**Why good**: `asyncio.Event` for shutdown signaling avoids polling a flag.
`CancelledError` ensures the task unwinds properly.

### 3.2 Concurrent Request Handling with Task Tracking

**Where**: `ingestion/service.py`

```python
spawned: set[asyncio.Task[None]] = set()

task = asyncio.create_task(_handle_one(request, source_app))
spawned.add(task)
task.add_done_callback(spawned.discard)
```

**Why good**: Each request runs independently. Slow requests don't block others.
The `done_callback` pattern keeps the tracking set clean without polling.

**Minor improvement**: Add `name=f"handler_{request.event_id}"` for debugging.

### 3.3 Strategy State Machine with Multi-Future Race

**Where**: `executor/core/execution_handler/strategy_execution/`

```python
done, pending = await asyncio.wait(
    [order_monitoring_task, price_dir_change_task, market_close_task],
    return_when=asyncio.FIRST_COMPLETED,
)
await self._cancel_pending_tasks(pending)
finished_task = done.pop()
```

**Why good**: This is the canonical use case for `asyncio.wait()` —
multiple concurrent monitors racing to complete. State machine pattern maps
cleanly to `FIRST_COMPLETED` semantics.

**Note**: This cannot be replaced by `asyncio.timeout()` or `asyncio.TaskGroup`
because the race semantic (first of N wins) and task-dispatch pattern (look up
the winner in a map) are intentional.

### 3.4 Async Queue for Producer-Consumer Decoupling

**Where**: `ingestion/adapters/alpaca/stream.py`, `executor/adapters/broker/alpaca/`

```python
self._queue: asyncio.Queue[Trade] = asyncio.Queue()

# Producer (callback — runs on foreign thread)
async def _on_trade(self, data: object) -> None:
    await self._queue.put(trade)

# Consumer (async generator)
async def stream(self) -> AsyncIterator[Trade]:
    while self._running:
        try:
            item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            yield item
        except TimeoutError:
            continue
```

**Why good**: Decouples WebSocket receive (callback thread) from data processing
(event loop). The timeout in `get()` allows checking `self._running` periodically
for graceful shutdown.

### 3.5 `asyncio.Lock` for Per-Row Database Isolation

**Where**: `executor/adapters/db/repositories/order_repo.py`

```python
self._locks: dict[UUID, asyncio.Lock] = {}

def _get_lock(self, order_id: UUID) -> asyncio.Lock:
    if order_id not in self._locks:
        self._locks[order_id] = asyncio.Lock()
    return self._locks[order_id]

async def update_order(self, order_id: UUID, ...) -> None:
    async with self._get_lock(order_id):
        await self._db.execute(...)
```

**Why good**: `asyncio.Lock` ensures that two concurrent coroutines don't
interleave updates to the same order row. The lock-per-row pattern avoids a
global bottleneck.

### 3.6 `asyncio.Event` for Strategy-Level Signaling

**Where**: `executor/core/execution_handler/strategy_execution/`

```python
self.exit_event = self.ctx.time_keeper.get_warning_event(min_minutes_remaining)

# Used as a "wait for market close or breakout" signal
market_close_task = asyncio.create_task(self.exit_event.wait())
```

**Why good**: `asyncio.Event` is the cheapest signaling mechanism in asyncio.
No polling, no queue overhead. Used correctly as a one-shot signal.

### 3.7 Retry with Bounded Attempts and Jitter

**Where**: SDK `retry.py`, various strategy handlers

```python
async def _retry(fn: Callable[[], Awaitable[T]], *, attempts: int = 3) -> T:
    for i in range(attempts):
        try:
            return await fn()
        except TransientError:
            if i == attempts - 1:
                raise
            await asyncio.sleep(2 ** i + random.uniform(0, 1))  # jitter
```

**Rules**:
- Never retry `CancelledError` or `KeyboardInterrupt` — these are shutdown signals
- Always bound retry attempts (3 is a good default)
- Always add jitter to avoid thundering herd on recovery
- Prefer explicit retry wrappers over hidden implicit loops

---

## 4. Anti-Patterns (What We Avoid)

### 4.1 ⛔ `asyncio.wait()` with a single future

```python
# ❌ Overkill — designed for multiple futures
done, _ = await asyncio.wait([future], timeout=timeout)

# ✅ Direct await with timeout
async with asyncio.timeout(timeout):
    return await future
```

### 4.2 ⛔ `asyncio.Queue` where `queue.Queue` suffices

If the producer is on a foreign thread and the consumer is on the event loop,
use `queue.Queue` (thread-safe) not `asyncio.Queue` (requires event loop).

```python
# ✅ Thread-safe for librdkafka callbacks
self._error_queue: queue.Queue[str] = queue.Queue()
```

### 4.3 ⛔ `asyncio.as_completed()` for our use cases

We don't have patterns where we need to process results as they complete in
arbitrary order. Our races are always "first wins, cancel rest" or "wait for
all". Avoid `asyncio.as_completed()` — it adds complexity without benefit here.

### 4.4 ⛔ `asyncio.TaskGroup` for dynamic task sets

`asyncio.TaskGroup` requires all tasks to be created in the `async with` block.
For dynamically-spawned tasks (e.g., per-request handlers), use manual
`create_task()` + tracking set + `add_done_callback`.

### 4.5 ⛔ Mixing `asyncio.run()` and `asyncio.Runner` in the same process

Pick one. All our entry points currently use `asyncio.run(main())`. That's fine
for single-loop applications. Don't introduce `asyncio.Runner` unless you have a
specific need for multi-loop or sequential coroutine execution.

### 4.6 ⛔ Unbounded `asyncio.gather()` on dynamic input

```python
# ❌ Memory risk — 10K requests = 10K concurrent tasks
results = await asyncio.gather(*(handle(r) for r in all_requests))

# ✅ Use a semaphore or bounded queue
sem = asyncio.Semaphore(20)
async def _bounded(r):
    async with sem:
        return await handle(r)
results = await asyncio.gather(*(_bounded(r) for r in all_requests))
```

### 4.7 ⛔ `except Exception` that swallows `CancelledError`

```python
# ❌ CancelledError is a BaseException subclass, but this pattern
#    is dangerous — future Python versions may change this
try:
    await work()
except Exception:              # Doesn't catch CancelledError today,
    pass                        # but hides unexpected failures

# ✅ Always re-raise or log cancellation
try:
    await work()
except asyncio.CancelledError:
    raise                       # Must propagate
except Exception:
    logger.exception("Work failed")
```

### 4.8 ⛔ Fire-and-forget for critical state transitions

Never use fire-and-forget (`create_task` without tracking) for:
- Order lifecycle events (submit, fill, cancel)
- Risk checks or position updates
- Any state transition requiring confirmation

```python
# ❌ If the task silently fails, the order is lost
asyncio.create_task(submit_order(order))

# ✅ Track the task and handle failure
order_task = asyncio.create_task(submit_order(order), name=f"order_{order.id}")
order_task.add_done_callback(_handle_order_result)
```

Use fire-and-forget only for best-effort notifications (telemetry, non-critical logging).

---

## 5. Concrete Improvement Recommendations

### 5.1 🔴 Ingestion: Replace `loop.run_in_executor(None, ...)` with `asyncio.to_thread()`

**Files**: `tradingcz/ingestion/adapters/alpaca/historical.py` (7 locations),
`tradingcz/ingestion/adapters/alpaca/option_historical.py` (4 locations)

**Current** (repeated 11 times):
```python
loop = asyncio.get_running_loop()
raw = await loop.run_in_executor(None, lambda: client.get_stock_bars(request))
```

**Recommended**:
```python
raw = await asyncio.to_thread(client.get_stock_bars, request)
```

**Impact**: Zero behavioral change. Reduces 2 lines → 1 line per call. Saves
~22 lines of boilerplate across the two files. `asyncio.to_thread()` passes
positional arguments directly — no lambda needed.

### 5.2 🟡 Ingestion: Name background tasks for debugging

**File**: `tradingcz/ingestion/service.py`

**Current**:
```python
task = asyncio.create_task(_handle_one(request, source_app))
```

**Recommended**:
```python
task = asyncio.create_task(_handle_one(request, source_app),
                           name=f"handle_{request.event_id}")
```

**Impact**: Makes `python -m asyncio ps PID` output meaningful in k3s pods.

### 5.3 🟡 Executor: Replace `loop.create_future()` with `asyncio.Future()`

**File**: `executor/adapters/market_data/market_data_dispatcher.py:124`

**Current**:
```python
loop = asyncio.get_running_loop()
future = loop.create_future()
```

**Recommended**:
```python
future = asyncio.Future()  # Python 3.14+ — binds to running loop automatically
```

**Impact**: Minor. `asyncio.Future()` works since Python 3.5.1. The explicit
`loop.create_future()` is redundant but harmless.

### 5.4 🟢 Consider `asyncio.timeout()` for `asyncio.wait_for()` usages

**File**: `ingestion/adapters/alpaca/stream.py:81`

**Current**:
```python
item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
```

This is actually fine — `wait_for` is concise for single-expression timeouts.
But if you're adding logging or cleanup on timeout, switch to:

```python
try:
    async with asyncio.timeout(1.0):
        item = await self._queue.get()
except TimeoutError:
    continue
```

### 5.5 🟢 Potential Future: `asyncio.TaskGroup` for strategy "all-of-N" patterns

Some strategy code does "create N tasks, wait for all":

```python
# executor/single_order_handler.py
monitoring_tasks: list[asyncio.Task] = []
# ... create tasks ...
await asyncio.wait(monitoring_tasks, return_when=asyncio.ALL_COMPLETED)
```

For **NEW** code with a fixed set of tasks created together, consider:

```python
async with asyncio.TaskGroup() as tg:
    t1 = tg.create_task(monitor_order(id1))
    t2 = tg.create_task(monitor_order(id2))
# All tasks done (or cancelled) when exiting the block
```

**Don't retrofit** existing code unless you're rewriting. The manual approach
works correctly and changing it adds risk without benefit.

---

## 6. Decision Matrix — Which Asyncio Primitive To Use

| Scenario | Primitive | Example |
|----------|-----------|---------|
| Run sync code in thread pool | `asyncio.to_thread()` | Alpaca REST API calls |
| Single future with timeout | `asyncio.timeout()` | Request-reply pattern |
| Multiple futures, first wins | `asyncio.wait(FIRST_COMPLETED)` | Strategy breakout monitoring |
| Multiple futures, all must finish | `asyncio.gather()` | Parallel data fetches |
| Multiple futures, all must finish (cleanup) | `asyncio.gather(return_exceptions=True)` | Task cancellation during shutdown |
| Fixed set of tasks, structured lifecycle | `asyncio.TaskGroup` | New code with N concurrent subtasks |
| Dynamic tasks (per request) | `create_task()` + `add_done_callback` | Per-request handlers |
| Producer-consumer (single event loop) | `asyncio.Queue` | WebSocket → processing pipeline |
| Producer-consumer (cross-thread) | `queue.Queue` (stdlib) | librdkafka callbacks |
| One-shot signal between coroutines | `asyncio.Event` | Shutdown, market close |
| Mutual exclusion between coroutines | `asyncio.Lock` | Per-row DB updates |
| Semaphore (limit concurrency) | `asyncio.Semaphore` | Rate-limited API calls |
| Sleep/delay | `asyncio.sleep()` | Polling intervals, retry backoff |
| Run entry point | `asyncio.run(main())` | `main.py` |
| Multiple sequential coroutines | `asyncio.Runner` | Advanced multi-loop scenarios |

---

## 7. Python 3.14+ Features Available To Us

| Feature | When to use | Priority |
|---------|------------|----------|
| **Task names in ps/pstree** | Debug stuck pods via `python -m asyncio ps PID` | 🟢 Use already |
| **`asyncio.Future()` (no loop needed)** | Creating futures anywhere | 🟡 Adopt gradually |
| **`create_task()` arbitrary kwargs** | Passing context/other args to task factory | 🔮 Future |
| **Free-threading** | Parallel event loops (when needed) | 🔮 Future (k3s) |
| **`capture_call_graph()`** | Debugging complex task trees | 🔮 Future |
| **`asyncio.timeout()` (3.11+)** | Preferred over `wait_for` for blocks | 🟢 Use now |
| **Exception groups in TaskGroup** | When TaskGroup raises grouped failures, classify transient vs permanent before retry | 🟡 Adopt with TaskGroup |
| **Cancellation observability** | Log cancellation with context (service, topic, correlation ID) for incident analysis | 🟡 Adopt now |

### Cancellation observability example

```python
try:
    await do_work()
except asyncio.CancelledError:
    logger.info(
        "Task cancelled: service=%s topic=%s corr_id=%s",
        self.service_id, self._topic, getattr(ctx, 'event_id', '?'),
    )
    raise  # Always propagate

### Deprecated (removal in Python 3.16) — we don't use these

| Deprecated API | Replacement | Our status |
|---------------|-------------|------------|
| `asyncio.iscoroutinefunction()` | `inspect.iscoroutinefunction()` | ✅ Not used |
| Event loop policy system | `asyncio.run(loop_factory=...)` | ✅ Not used |
| Child watchers | N/A (removed in 3.14) | ✅ Not used |
| `asyncio.get_event_loop()` (no loop) | `asyncio.get_running_loop()` | ✅ Always have a loop |

---

## 8. Trading-System Defaults

Use these defaults unless there is a documented reason to diverge.

| Concern | Default | Rationale |
|---------|---------|-----------|
| **Timeouts** | Always set; no unbounded network await | Fail fast under market stress |
| **Concurrency** | Bounded by semaphore or queue capacity | Prevent memory exhaustion from spikes |
| **Reliability** | Request/reply for critical state changes | Order lifecycle, risk, position updates |
| **Best-effort** | Fire-and-forget only for non-critical events | Telemetry, non-critical logging |
| **Shutdown** | Graceful stop tested under in-flight load | Drain → flush → close, idempotent |
| **Observability** | Include service ID, topic, message type, correlation ID in async error logs | Production incident analysis |

---

## 9. Quick Checklist for Code Review

When reviewing async code in any repo, check:

- [ ] `ensure_future()` not called from foreign thread
- [ ] `loop.run_in_executor(None, ...)` replaced with `asyncio.to_thread()`
- [ ] `asyncio.wait([single_future])` replaced with direct await + `asyncio.timeout()`
- [ ] `asyncio.wait()` only used for multi-future races
- [ ] All `create_task()` call sites have CancelledError handling
- [ ] Tasks are named (`name=...`) for observability
- [ ] Concurrency is bounded (semaphore or bounded queue) — no unbounded `gather()`
- [ ] Shutdown path is idempotent (safe to call twice)
- [ ] `asyncio.gather()` with `return_exceptions=True` during shutdown
- [ ] Cross-thread callbacks use `queue.Queue` or `run_coroutine_threadsafe`
- [ ] No `asyncio.as_completed()` (anti-pattern for our use cases)
- [ ] Fire-and-forget only for best-effort; critical state uses request/reply
- [ ] Retry has bounded attempts + jitter; `CancelledError` never retried
- [ ] Cancellation is logged with context for observability
- [ ] `asyncio.run()` at entry point; no mixing with `Runner` unnecessarily
