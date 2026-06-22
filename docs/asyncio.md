# Asyncio Best Practices — Trading System (Python 3.14+)

> Scope: all trading-cz repos. Target: Python ≥3.14. Runtime: k3s pods + Kafka + market data streaming.  
> One rule of thumb: **use asyncio to reduce code and fix bugs — don't use features just because they exist.**

---

## Core Rules

1. **One event loop per process** — `asyncio.run(main())` at entry. Never nest loops.
2. **`asyncio.to_thread()` for sync code** — never `loop.run_in_executor(None, ...)`. Same result, fewer lines. SDK already migrated; ingestion still needs it (11 instances in Alpaca adapters).
3. **`asyncio.timeout()` for single awaitables** — cleaner than `asyncio.wait_for()` for blocks. `wait_for` is fine for one-liner expressions (`await asyncio.wait_for(q.get(), timeout=1.0)`).
4. **`asyncio.wait()` only for multi-future races** — never `asyncio.wait([single_future])`. Use `await future` directly (with `asyncio.timeout()` if needed).
5. **Thread-safe callbacks only** — `asyncio.ensure_future()` is NOT thread-safe. From foreign threads use: `queue.Queue.put()` (fire-and-forget), `asyncio.run_coroutine_threadsafe()` (need response), or `asyncio.to_thread()` (blocking→async).
6. **Bound concurrency** — cap with `asyncio.Semaphore` or `asyncio.Queue(maxsize=N)`. Never unbounded `gather()` on dynamic input — memory risk under market data spikes.
7. **`CancelledError` must propagate** — every background task handles it at the top level. Shutdown: cancel tasks → `await asyncio.gather(*tasks, return_exceptions=True)` → close.
8. **Idempotent shutdown** — safe to call `close()` twice. Pattern: `if self._closed: return` → flush → close connections.
9. **Named tasks** — always `asyncio.create_task(coro, name="...")`. Enables `python -m asyncio ps PID` debugging.
10. **Retry with bounds + jitter** — max 3 attempts, exponential backoff + random jitter. Never retry `CancelledError`.

## When To Use Each Primitive

| Scenario | Primitive |
|----------|-----------|
| Sync code in thread pool | `asyncio.to_thread()` |
| Single future + timeout | `asyncio.timeout()` |
| Multiple futures, first wins | `asyncio.wait(FIRST_COMPLETED)` |
| Multiple futures, all must finish | `asyncio.gather()` |
| Cancel + drain N tasks | `asyncio.gather(*tasks, return_exceptions=True)` |
| Fixed N subtasks, structured lifecycle | `asyncio.TaskGroup` (new code only) |
| Dynamic tasks (per-request) | `create_task()` + `add_done_callback` |
| Producer-consumer, single event loop | `asyncio.Queue` |
| Producer-consumer, cross-thread | `queue.Queue` (thread-safe) |
| One-shot signal | `asyncio.Event` |
| Mutual exclusion | `asyncio.Lock` |
| Rate limit | `asyncio.Semaphore` |
| Entry point | `asyncio.run(main())` |

## Anti-Patterns — Never Do This

- `asyncio.wait([single_future])` — use `await future` or `asyncio.timeout()`
- `asyncio.ensure_future()` from a non-event-loop thread
- `asyncio.Queue` where `queue.Queue` suffices (cross-thread fire-and-forget)
- `asyncio.as_completed()` — we don't have "process as they complete" patterns
- `asyncio.TaskGroup` for dynamically-spawned tasks — use `create_task()` + tracking set
- Unbounded `asyncio.gather(*[h(r) for r in huge_list])` — cap with `Semaphore`
- `except Exception` without re-raising `CancelledError`
- Fire-and-forget for order lifecycle, risk, or state transitions — use request/reply with confirmation
- Mixing `asyncio.run()` and `asyncio.Runner` in the same process — pick one

## Trading-System Defaults

| Concern | Default |
|---------|---------|
| Timeouts | Always set; no unbounded network await |
| Concurrency | Bounded by semaphore or queue capacity |
| Reliability | Request/reply for critical state; fire-and-forget only for telemetry |
| Shutdown | Drain → flush → close; idempotent |
| Observability | Log cancellations with service, topic, correlation ID |

## Code Review Checklist

- [ ] `asyncio.to_thread()` not `loop.run_in_executor(None, ...)`
- [ ] `asyncio.timeout()` not `asyncio.wait([single_future])`
- [ ] `asyncio.wait()` only for multi-future races
- [ ] All `create_task()` sites handle `CancelledError`
- [ ] Tasks are named
- [ ] Concurrency is bounded (semaphore or bounded queue)
- [ ] Shutdown is idempotent
- [ ] Cancellation is logged with context
- [ ] Retry has bounded attempts + jitter; `CancelledError` never retried
- [ ] Cross-thread callbacks use `queue.Queue` or `run_coroutine_threadsafe`
- [ ] Fire-and-forget only for non-critical events
