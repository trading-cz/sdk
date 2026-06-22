# Asyncio Best Practices for Trading Services

This guide defines the asyncio rules for services built on `tradingcz/sdk`.

## 1) Core Rules

1. **One event loop per process**
   - Use `asyncio.run(main())` once at process entry.
   - Do not nest event loops.
2. **Structured lifecycle**
   - Prefer `async with` for components with start/stop behavior.
   - Always close producers/consumers/admin clients explicitly.
3. **Cancellation is part of normal control flow**
   - Re-raise `CancelledError` immediately.
   - Never silently swallow cancellation.
4. **Bound all waits**
   - Use timeouts for network I/O and request/reply flows.
   - Fail fast, log context, and let callers decide retry strategy.
5. **Do not block the loop**
   - No `time.sleep`, heavy CPU loops, or blocking client calls in coroutines.
   - Offload blocking work to a thread/process executor when unavoidable.
6. **Backpressure first**
   - Use bounded queues/semaphores to cap concurrent in-flight work.
   - Keep ingestion pressure below downstream capacity.
7. **Idempotent shutdown**
   - Shutdown paths must be safe when called multiple times.
   - Drain tasks, flush producers, then close transports.

## 2) Documented Patterns

### A) Service lifecycle pattern

- Wrap service runtime in `async with ServiceApp(...)`.
- Register all long-lived tasks in one place.
- Coordinate shutdown via `asyncio.Event` + signal handlers.

### B) Request/Reply pattern

- Use bounded request timeout and correlation IDs.
- Keep per-request task scope small and cancellable.
- Treat timeout as expected behavior under market stress.

### C) Fire-and-forget pattern

- Use only for non-critical notifications and telemetry.
- If delivery matters, use request/reply or explicit acknowledgement flow.

### D) Consumer worker pool pattern

- Feed messages into bounded `asyncio.Queue`.
- Run fixed-size worker tasks.
- Commit offsets only after successful handling policy is applied.

### E) Retry pattern

- Retry transient failures with bounded attempts and jitter.
- Never retry `CancelledError` / `KeyboardInterrupt`.
- Prefer explicit retry wrappers over hidden implicit loops.

## 3) Anti-Patterns (Do Not Use)

1. `asyncio.create_task(...)` without tracking task handle.
2. Infinite `while True` loops without cancellation checkpoints.
3. Unbounded fan-out (`gather` on arbitrarily large input).
4. Global mutable state shared across unrelated coroutines without protection.
5. Blocking SDKs/DB drivers called directly inside async handlers.
6. Catch-all `except Exception` blocks that also consume cancellation context.
7. Fire-and-forget for order lifecycle, risk, or state transitions requiring confirmation.

## 4) Decision Matrix

| Situation | Recommended Pattern | Why |
| --- | --- | --- |
| Startup/shutdown of service resources | `async with` lifecycle blocks | Guarantees deterministic cleanup |
| Low-latency request needing response | Request/Reply + timeout | Correlation + explicit failure path |
| High-volume independent jobs | Bounded queue + worker pool | Backpressure + predictable memory |
| Small fixed parallel calls | `asyncio.TaskGroup` | Structured concurrency + safe cancellation |
| Best-effort notification | Fire-and-forget | Lower overhead when loss is acceptable |
| Transient remote error | Bounded retry with jitter | Reduces burst collapse and thundering herds |
| CPU-heavy transformation | `run_in_executor` / process pool | Prevents event-loop starvation |

## 5) Python 3.14+ Recommendations

1. **Use `asyncio.TaskGroup` as default for sibling tasks**
   - Prefer over ad-hoc `create_task` + manual join/cancel logic.
2. **Use `asyncio.timeout()` for scoped time limits**
   - Keep timeout scope local and explicit.
3. **Use exception groups intentionally**
   - When TaskGroup raises grouped failures, classify transient vs permanent causes before retry.
4. **Prefer modern type hints for async APIs**
   - Use built-in generics (`list[T]`, `dict[str, T]`) and current Python 3.14 typing style.
5. **Prepare for free-threaded evolution conservatively**
   - Keep async code race-safe (avoid unsafe shared mutable state), even if services run with a GIL today.
6. **Keep cancellation observable**
   - Log cancellation with task context (service, topic, correlation ID) for production incident analysis.

## 6) Minimal Checklist for New Async Components

- [ ] Entry point uses a single `asyncio.run(...)`.
- [ ] Lifecycle is explicit (`start`/`stop` or `async with`).
- [ ] All external I/O has timeout and retry policy (or explicit no-retry decision).
- [ ] Background tasks are tracked and cancelled on shutdown.
- [ ] Work queues/concurrency are bounded.
- [ ] `CancelledError` is propagated.
- [ ] Logging includes correlation context for failures/timeouts.

## 7) Trading-System Defaults

Use these defaults unless there is a documented reason to diverge:

- **Timeouts:** always set; no unbounded network await.
- **Concurrency:** bounded by semaphore/queue capacity.
- **Reliability:** request/reply for critical state changes; fire-and-forget only for best-effort events.
- **Shutdown:** graceful stop path tested under in-flight load.
- **Observability:** include service ID, topic, message type, and correlation ID in async error logs.
