# health — Service Health (Lifecycle Publisher + Monitor)

| Class | Role | Key API |
| ------- | ------ | --------- |
| `HealthPublisher` | Emit lifecycle events for **this** service | `initializing()` → `ready()` → `heartbeat()` → `down()` |
| `HealthMonitor` | Track liveness of **other** services | `on(state, cb, *, ttl)`, `on_event(event)`, `start()`, `stop()` |

## HealthPublisher

```text
initializing()  → INITIALIZING
ready()         → READY + heartbeat loop starts
heartbeat()     → force HEARTBEAT now + reset interval timer
down()          → DOWN + heartbeat loop stops
```text

```python
health = HealthPublisher(faf, "my-service", interval=300)
await health.initializing()
await health.ready()
await health.heartbeat()    # manual, resets timer
await health.down()
```text

## HealthMonitor

Pure logic — no Kafka, no EventRouter.  Caller feeds events via `on_event()`.

States you can register for:
- `LifecycleEventType.INITIALIZING`
- `LifecycleEventType.READY`
- `LifecycleEventType.HEARTBEAT`
- `LifecycleEventType.DOWN`
- `LifecycleEventType.EXPIRED` — monitor-internal, not a wire event

```python
monitor = HealthMonitor(sweep_interval=60)

# TTL only on EXPIRED — default 600s if omitted
monitor.on(LifecycleEventType.EXPIRED, handle_expired, ttl=600)
monitor.on(LifecycleEventType.READY, handle_ready)

# Feed events from wherever they come
router.on(EventType.SERVICE_LIFECYCLE, LifecycleEvent,
          handler=lambda ev, _: monitor.on_event(ev))

await monitor.start()
await router.run()
await monitor.stop()
```text

> Caller owns the EventRouter.  `on_event()` returns immediately
> (callbacks are `create_task`'d).  No EXPIRED registration → sweep
> is a no-op.
