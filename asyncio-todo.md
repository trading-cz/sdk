# SDK Asyncio Audit & Modernization Plan — Python 3.14

> **Context**: SDK targets `requires-python = ">=3.14"` (see `pyproject.toml`).  
> All Python 3.9–3.14 asyncio features are available.  
> The SDK runs on **k3s** (lightweight Kubernetes) with Kafka — correctness and non-blocking behavior are critical.  
> **📖 Companion guide**: [`docs/asyncio.md`](docs/asyncio.md) — comprehensive asyncio best practices for the entire trading system.

---

## 📋 Implementation Status (2026-06-22)

| # | Change | Status | Notes |
|---|--------|--------|-------|
| 2 | 🔴 `ensure_future()` bug fix | ✅ **DONE** | Option B applied. `_handle_error` uses `queue.Queue.put()` only. `_on_error` parameter removed from `TransportProducer`. |
| 3 | 🟡 `loop.run_in_executor()` → `to_thread()` | ✅ **DONE** | All 3 locations now use `asyncio.to_thread()`. No `run_in_executor` found anywhere in SDK. |
| 4 | 🟡 `asyncio.wait()` → `asyncio.timeout()` | ✅ **DONE** | `request_reply.py` uses `async with asyncio.timeout(timeout)`. No `asyncio.wait()` found. |
| 5 | 🟡 `asyncio.run()` → `asyncio.Runner` | ⬜ **Deferred** | Outside SDK scope — downstream repos (simple-strategy, ingestion, executor, risk, testing). |

### 🔍 Consumer-Side `_on_error` Clarification

The `_on_error` parameter on `TransportConsumer`, `TypedConsumer`, and `Router` is **NOT buggy** and intentionally kept:
- These callbacks are `await`ed directly from the event loop context (running inside `poll()` which is async)
- They are actually used — `Router` passes `on_error` through to `TypedConsumer` at `router.py:158`
- The executor uses `_on_undispatchable` callback at `executor/main.py:156`
- **Unlike `TransportProducer._handle_error`** (which ran on librdkafka's foreign thread), the consumer callbacks run safely on the event loop

### Python 3.14 Asyncio News (from docs.python.org)

- **New**: `asyncio.capture_call_graph()` / `print_call_graph()` — introspection API for async call graphs
- **New CLI**: `python -m asyncio ps PID` / `pstree PID` — live task inspection without instrumentation
- **New**: `create_task()` now accepts arbitrary kwargs passed to Task constructor
- **Perf**: 10-20% improvement from new per-thread task linked list, reduced memory usage
- **Free-threading**: Officially supported — parallel event loops across threads now scale linearly
- **Removed (3.14)**: All child watcher classes; `get_event_loop()` now raises `RuntimeError` if no loop
- **Deprecated (removal in 3.16)**: `asyncio.iscoroutinefunction()` → use `inspect.iscoroutinefunction()`; policy system entirely deprecated
- **No impact on SDK**: None of these deprecations affect current SDK code (verified by grep)

---

## 1. Complete Inventory of Asyncio Patterns

| # | Pattern | Locations | Python 3.14 Status |
|---|---------|-----------|---------------------|
| 1 | `loop.run_in_executor(None, ...)` | ~~`transport_producer.py:70,81`~~, ~~`kafka_topic.py:72`~~ | ✅ **Fixed** — all use `asyncio.to_thread()` |
| 2 | `asyncio.ensure_future(...)` | ~~`transport_producer.py:126`~~ | ✅ **Fixed** — thread-safe `queue.Queue.put()` only |
| 3 | `asyncio.wait([future], timeout=...)` | ~~`request_reply.py:138`~~ | ✅ **Fixed** — uses `asyncio.timeout()` |
| 4 | `loop.create_future()` | `request_reply.py:134` | ⚠️ Verbose — `asyncio.get_running_loop().create_future()` is fine; `asyncio.Future()` also works in 3.14 |
| 5 | `asyncio.create_task(name=...)` | `router.py:113,213`, `publisher.py:44,57`, `monitor.py:69,76`, `clock.py:47` | ✅ Correct — named tasks are best practice |
| 6 | `asyncio.CancelledError` handling | `router.py:121`, `publisher.py:53,68,81`, `monitor.py:87,110`, `request_reply.py:88,179`, `service_app.py:222` | ✅ Correct — proper cancellation hygiene |
| 7 | `asyncio.Event` for shutdown | `service_app.py:54,128`, `async_utils.py:7`, `clock.py:42,61` | ✅ Correct |
| 8 | `asyncio.sleep()` for intervals/retries | `publisher.py:77`, `monitor.py:101`, `retry.py:50`, `clock.py:105` | ✅ Correct |
| 9 | `async for` / `__aiter__` / `__anext__` | `transport_consumer.py:74-97`, `router.py:205`, `request_reply.py:170`, `_base.py:59-72` | ✅ Correct |
| 10 | `async with` / `__aenter__` / `__aexit__` | `service_app.py`, `router.py`, `request_reply.py`, `kafka_topic.py`, `_base.py` | ✅ Correct |
| 11 | `ThreadPoolExecutor` explicit ownership | `transport_consumer.py:43-44` | ✅ Excellent — Python 3.14 segfault workaround |
| 12 | `loop.add_signal_handler()` | `async_utils.py:14` | ✅ Correct for k3s/Linux |
| 13 | `loop.time()` for deadlines | `transport_consumer.py:67,69` | ✅ Correct |
| 14 | `asyncio.run()` (in downstream repos) | `simple-strategy/main.py`, `ingestion/main.py`, `executor/main.py`, `risk/main.py`, `testing/main.py` | ⚠️ Fine for now — consider `asyncio.Runner` for multi-loop |

---

## 2. ✅ RESOLVED: Thread-Unsafe `asyncio.ensure_future()` in Delivery Callback

**File**: `tradingcz/sdk/transport/transport_producer.py`

**Resolution**: Option B was applied. The `_on_error` callback parameter was removed from `TransportProducer` entirely. The delivery callback now only uses thread-safe `queue.Queue.put()`. Callers retrieve errors via `drain_errors()`.

**Current code**:
```python
def _handle_error(self, err: object, msg: object) -> None:
    """Delivery callback — runs on librdkafka internal thread.
    Thread-safe: only uses thread-safe queue.Queue.put().
    """
    if err is not None:
        logger.error(...)
        self._error_queue.put(str(err))
```

**Severity**: ✅ Resolved — no production risk.

---

## 3. ✅ COMPLETED: `loop.run_in_executor()` → `asyncio.to_thread()`

All three locations now use `asyncio.to_thread()`:
- `transport_producer.py` — `send()` and `flush()`
- `kafka_topic.py` — `ensure()`

**Severity**: ✅ Completed.

---

## 4. ✅ COMPLETED: `asyncio.wait()` → `asyncio.timeout()`

`request_reply.py` now uses `async with asyncio.timeout(timeout)`.

**Severity**: ✅ Completed.

---

## 5. 🟡 Consideration: `asyncio.run()` → `asyncio.Runner` in Downstream Repos

**Files affected** (downstream — not in SDK):
- `simple-strategy/main.py:70`
- `ingestion/main.py:34`
- `executor/main.py:190,256`
- `risk/main.py:45`
- `testing/main.py:54`

**Current pattern**:
```python
asyncio.run(main())
```

**Python 3.14 alternative**:
```python
with asyncio.Runner() as runner:
    runner.run(main())
```

**Why**:
- `asyncio.Runner` (Python 3.11+) properly isolates the event loop per context
- Allows multiple sequential `run()` calls with proper cleanup
- In Python 3.14, `Runner` is the recommended way to run async code from sync context
- `asyncio.run()` is NOT deprecated but `Runner` is more robust for:
  - Multiple event loop cycles in one process
  - Debug mode (`Runner(debug=True)`)
  - Custom event loop factories

**When to switch**: If any service needs to run multiple async entry points sequentially, or if you enable `debug=True` for development. Otherwise, `asyncio.run()` remains fine.

**Severity**: 🟢 Informational — `asyncio.run()` is still valid in Python 3.14.

---

## 6. ✅ Patterns Already Correct (No Action Needed)

### 6.1 Named Tasks (`asyncio.create_task(name=...)`)
All `create_task()` calls use the `name` parameter. Python 3.14 debugging tools (e.g., `asyncio` debug mode, crash dumps) use task names for diagnostics.

**Verified in**: `router.py:113`, `router.py:213`, `clock.py:47`

### 6.2 CancelledError Hygiene
Every cancellation point properly catches `asyncio.CancelledError`, performs cleanup, and either propagates or suppresses appropriately.

**Verified in**: All files that spawn background tasks.

### 6.3 Async Context Managers (`async with`)
All resources that need cleanup use `__aenter__`/`__aexit__`. Python 3.14's `aclose()` protocol is fully supported.

**Verified in**: `service_app.py`, `router.py`, `request_reply.py`, `kafka_topic.py`, `_base.py`

### 6.4 Async Iterators (`async for`)
Kafka message consumption uses `__aiter__`/`__anext__` with proper `finally` cleanup. Python 3.14's `anext()` built-in and `StopAsyncIteration` handling are correct.

**Verified in**: `transport_consumer.py`, `router.py`, `request_reply.py`

### 6.5 ThreadPoolExecutor Ownership (Python 3.14 Segfault Workaround)
`TransportConsumer` explicitly owns its `ThreadPoolExecutor` because `AIOConsumer` in confluent-kafka 2.14.2 leaks its internal executor, causing segfaults on Python 3.14. The split `shutdown(wait=False)` / `shutdown(wait=True)` pattern avoids deadlocks during async iteration cleanup.

**Verified in**: `transport_consumer.py:43-44,95,107`

### 6.6 Producer/AdminClient Reference Retention (Python 3.14 Segfault Workaround)
Both `TransportProducer.close()` and `KafkaTopicAdmin.close()` intentionally keep the underlying C object reference alive to avoid `__del__` segfaults on Python 3.14.

**Verified in**: `transport_producer.py:89-98`, `kafka_topic.py:130-138`

### 6.7 Signal Handling
`loop.add_signal_handler()` with `asyncio.Event` is the correct pattern for k3s/Linux. Python 3.14's signal handling is unchanged from 3.12+.

**Verified in**: `async_utils.py:7-18`

---

## 7. What Python 3.14 DOES NOT Change for This SDK

| Feature | Status |
|---------|--------|
| `asyncio.ensure_future()` deprecation | **Not deprecated** — still available but `create_task()` is preferred |
| `asyncio.run()` deprecation | **Not deprecated** — `Runner` is preferred but `run()` remains |
| `loop.run_in_executor()` deprecation | **Not deprecated** — `to_thread()` is preferred but `run_in_executor()` remains |
| `asyncio.wait()` deprecation | **Not deprecated** — `timeout()`/`wait_for()` are preferred for single-future cases |
| `loop.add_signal_handler()` removal | **Not removed** — still the correct API for Unix signal handling |
| `TaskGroup` required for new code | **Strongly recommended** but not enforced — existing `create_task`/`cancel` patterns still valid |

---

## 8. Prioritized Action Items

| # | Priority | Action | File(s) | Effort |
|---|----------|--------|---------|--------|
| 1 | 🔴 **P0** | Fix thread-unsafe `ensure_future()` in delivery callback | `transport_producer.py:126` | Small |
| 2 | 🟡 **P1** | Replace `loop.run_in_executor(None, ...)` with `asyncio.to_thread()` | `transport_producer.py:70,81`, `kafka_topic.py:72` | Small |
| 3 | 🟡 **P1** | Replace `asyncio.wait([future], timeout=...)` with `asyncio.timeout()` | `request_reply.py:134-143` | Small |
| 4 | 🟢 **P2** | Consider `asyncio.Runner` in downstream `main.py` files | `simple-strategy/`, `ingestion/`, `executor/`, `risk/`, `testing/` | Small |

---

## 9. Final Verdict

| Dimension | Rating | Notes |
|-----------|--------|-------|
| **Correctness** | ⚠️ 9/10 | One thread-safety bug (P0 — see Section 2) |
| **Non-blocking** | ✅ 10/10 | All I/O properly offloaded to threads |
| **Deadlock safety** | ✅ 10/10 | No circular awaits; proper `CancelledError` handling |
| **Resource cleanup** | ✅ 10/10 | `async with` + `finally` everywhere; explicit executor lifecycle |
| **Python 3.14 compat** | ✅ 10/10 | Explicit segfault workarounds for confluent-kafka |
| **API modernity** | 🟡 7/10 | Uses pre-3.11 patterns (3 files affected, all cosmetic) |
| **Trading workload ready** | ✅ 9/10 | Safe for production **after fixing P0 bug** |

**Summary**: The SDK's async architecture is fundamentally sound and safe for high-load trading on k3s. One thread-safety bug must be fixed before production use. The remaining items are style/readability improvements that bring the codebase in line with Python 3.14's recommended asyncio idioms — they are not urgent but should be addressed during normal maintenance cycles.
