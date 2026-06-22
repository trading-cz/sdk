# Asyncio Best Practices — Trading System (Python 3.14+)

> Scope: all trading-cz repos. Target: Python ≥3.14.  
> Runtime: k3s pods, Kafka messaging, strategy execution, market data streaming.  
> Rule of thumb: **use asyncio to reduce code and fix bugs — don't use features just because they exist.**

---

## 1. Philosophy

If a simpler synchronous approach works equally well (e.g., `queue.Queue.get_nowait()` vs
`asyncio.Queue`), prefer the simpler one.

**Decision hierarchy:**
```
1. Does this need to be async at all? I/O → YES. CPU/memory → NO, use thread executor.
2. Single awaitable + timeout → asyncio.timeout()
3. Multi-future race → asyncio.wait(FIRST_COMPLETED)
4. Multi-future all → asyncio.gather()
5. Thread offload → asyncio.to_thread()
6. Cross-thread callback → queue.Queue.put() or asyncio.run_coroutine_threadsafe()
```

---

## 2. Core Rules (Must Follow)

### 2.1 Never `asyncio.ensure_future()` from a foreign thread 🔴

`ensure_future()` is not thread-safe. From librdkafka/WebSocket callbacks, use:

```python
# ✅ Thread-safe fire-and-forget — let event loop drain errors
self._error_queue: queue.Queue[str] = queue.Queue()
self._error_queue.put(str(err))

# ✅ Need response from event loop
asyncio.run_coroutine_threadsafe(self._on_error(err), loop)

# ✅ Blocking → async
result = await asyncio.to_thread(sync_func)
```

### 2.2 `asyncio.to_thread()` over `loop.run_in_executor(None, ...)` 🟡

```python
# ❌ Old — 2 extra lines, lambda noise
loop = asyncio.get_running_loop()
raw = await loop.run_in_executor(None, lambda: client.get_stock_bars(request))

# ✅ New — passes args directly, no lambda needed
raw = await asyncio.to_thread(client.get_stock_bars, request)
```

**Status**: SDK ✅, Executor ✅, **Ingestion ❌** — 11 instances in Alpaca adapters.

### 2.3 `asyncio.timeout()` over `asyncio.wait_for()` for blocks 🟡

```python
# ❌ Verbose
try:
    result = await asyncio.wait_for(something(), timeout=10)
except TimeoutError:
    ...

# ✅ Structured — timeout scope is explicit
try:
    async with asyncio.timeout(10):
        result = await something()
except TimeoutError:
    ...
```

`wait_for()` is fine for simple one-liners: `await asyncio.wait_for(q.get(), timeout=1.0)`.

### 2.4 `asyncio.wait()` only for multi-future races 🟢

```python
# ✅ Correct — FIRST_COMPLETED among N tasks
done, pending = await asyncio.wait(
    [order_task, price_task, close_task],
    return_when=asyncio.FIRST_COMPLETED,
)
winner = done.pop()
await asyncio.gather(*pending, return_exceptions=True)  # cancel rest

# ❌ Wrong — single future
done, _ = await asyncio.wait([future], timeout=...)  # use asyncio.timeout() instead
```

### 2.5 Bound concurrency — backpressure first 🔴

Never unbounded `gather()` on dynamic input. Market data spikes produce thousands of
messages/second — unbounded fan-out causes memory exhaustion.

```python
# ❌ 10K requests = 10K concurrent tasks
results = await asyncio.gather(*(handle(r) for r in all_requests))

# ✅ Cap with semaphore
sem = asyncio.Semaphore(20)
async def _bounded(r):
    async with sem:
        return await handle(r)
results = await asyncio.gather(*(_bounded(r) for r in all_requests))
```

### 2.6 Idempotent shutdown 🔴

Safe to call `close()` twice. Pattern: `if self._closed: return` → flush → close.

```python
async def close(self) -> None:
    if self._closed:
        return
    self._closed = True
    await self._producer.flush()
    # ... close connections ...
```

### 2.7 `CancelledError` must propagate 🔴

Every background task handles it at top level. Shutdown: cancel → await → close.

```python
async def _loop() -> None:
    try:
        while True:
            await do_work()
    except asyncio.CancelledError:
        logger.info("Loop cancelled")
        raise  # Always propagate

# Shutdown
for task in pending:
    task.cancel()
await asyncio.gather(*pending, return_exceptions=True)
```

### 2.8 Named tasks 🟢

```python
task = asyncio.create_task(_loop(), name="event_router")
```
Enables `python -m asyncio ps PID` for live task inspection in k3s pods.

### 2.9 Retry with bounds + jitter 🟡

```python
async def _retry(fn, *, attempts=3):
    for i in range(attempts):
        try:
            return await fn()
        except TransientError:
            if i == attempts - 1:
                raise
            await asyncio.sleep(2 ** i + random.uniform(0, 1))  # jitter
```

Never retry `CancelledError` — it's a shutdown signal, not a transient failure.

---

## 3. Patterns (with Code Examples)

### 3.1 Background Loop + Shutdown Event

```python
async def serve(self) -> None:
    router_task = asyncio.create_task(self._loop(), name="router")
    await self._shutdown.wait()          # asyncio.Event — no polling
    router_task.cancel()
    await router_task                    # ensures cleanup completes
```

### 3.2 Concurrent Requests with Task Tracking

```python
spawned: set[asyncio.Task[None]] = set()
task = asyncio.create_task(_handle_one(request), name=f"req_{request.event_id}")
spawned.add(task)
task.add_done_callback(spawned.discard)  # auto-cleanup, no polling
```

### 3.3 Strategy State Machine with Multi-Future Race

```python
done, pending = await asyncio.wait(
    [order_monitor, price_watch, market_close],
    return_when=asyncio.FIRST_COMPLETED,
)
await asyncio.gather(*pending, return_exceptions=True)  # cancel losers
winner = done.pop()
```

Cannot use `asyncio.timeout()` here — it's a "first of N wins" race, not a time limit.

### 3.4 `asyncio.Lock` for Per-Row DB Isolation

```python
self._locks: dict[UUID, asyncio.Lock] = {}

async def update_order(self, order_id, ...):
    async with self._get_lock(order_id):
        await self._db.execute(...)  # no interleaved writes to same row
```

### 3.5 `asyncio.Event` for Strategy Signaling

```python
self.exit_event = time_keeper.get_warning_event(min_before_close)
market_close_task = asyncio.create_task(self.exit_event.wait())
```
Cheapest signaling mechanism — no queue overhead, no polling.

---

## 4. Anti-Patterns (Never Do This)

| # | Anti-Pattern | Correct |
|---|-------------|---------|
| 1 | `asyncio.wait([single_future])` | `await future` or `asyncio.timeout()` |
| 2 | `asyncio.ensure_future()` from foreign thread | `queue.Queue.put()` or `run_coroutine_threadsafe()` |
| 3 | `asyncio.Queue` for cross-thread fire-and-forget | `queue.Queue` (stdlib, thread-safe) |
| 4 | `asyncio.TaskGroup` for dynamic task sets | `create_task()` + `add_done_callback` |
| 5 | Unbounded `gather()` on dynamic input | Cap with `asyncio.Semaphore` |
| 6 | `except Exception` without re-raising `CancelledError` | Always catch `CancelledError` first, re-raise |
| 7 | Fire-and-forget for order/risk/position state | Request/reply with confirmation |
| 8 | Mixing `asyncio.run()` and `asyncio.Runner` | Pick one; use `asyncio.run(main())` |
| 9 | `asyncio.as_completed()` | We don't have "process as completed" patterns |

---

## 5. Decision Matrix — Which Primitive

| Scenario | Primitive |
|----------|-----------|
| Sync code in thread pool | `asyncio.to_thread()` |
| Single future + timeout | `asyncio.timeout()` |
| Multiple futures, first wins | `asyncio.wait(FIRST_COMPLETED)` |
| Multiple futures, all must finish | `asyncio.gather()` |
| Cancel + drain N tasks | `asyncio.gather(*tasks, return_exceptions=True)` |
| Fixed N subtasks, structured lifecycle | `asyncio.TaskGroup` (new code only) |
| Dynamic per-request tasks | `create_task()` + `add_done_callback` |
| Producer-consumer, same loop | `asyncio.Queue` |
| Producer-consumer, cross-thread | `queue.Queue` (stdlib) |
| One-shot signal | `asyncio.Event` |
| Mutual exclusion | `asyncio.Lock` |
| Rate limit | `asyncio.Semaphore` |
| Entry point | `asyncio.run(main())` |

---

## 6. Trading-System Defaults

| Concern | Default |
|---------|---------|
| Timeouts | Always set; no unbounded network await |
| Concurrency | Bounded by semaphore or queue capacity |
| Reliability | Request/reply for critical state; fire-and-forget only for telemetry |
| Shutdown | Drain → flush → close; idempotent |
| Observability | Log cancellations with service, topic, correlation ID |

---

## 7. Code Review Checklist

- [ ] `asyncio.to_thread()` not `loop.run_in_executor(None, ...)`
- [ ] `asyncio.timeout()` not `asyncio.wait([single_future])`
- [ ] `asyncio.wait()` only for multi-future races
- [ ] All `create_task()` sites handle `CancelledError`
- [ ] Tasks are named (`name=...`)
- [ ] Concurrency is bounded (semaphore or bounded queue)
- [ ] Shutdown is idempotent
- [ ] Cancellation is logged with context
- [ ] Retry has bounds + jitter; `CancelledError` never retried
- [ ] Cross-thread callbacks use `queue.Queue` or `run_coroutine_threadsafe`
- [ ] Fire-and-forget only for non-critical events
