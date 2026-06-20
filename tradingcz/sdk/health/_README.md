# health — Service Health (Lifecycle Publisher + Monitor)

Two sides of the same coin:

| Class | Role | Key API |
|-------|------|---------|
| `HealthPublisher` | Emit lifecycle events for **this** service | `initializing()` → `ready()` → `down()` |
| `HealthMonitor` | Track liveness of **other** services | `on_down(cb)`, `start()`, `stop()` |

## HealthPublisher

Publishes the standard lifecycle sequence on the event topic:

```
initializing()  → INITIALIZING
ready()         → READY + heartbeat loop starts
  … heartbeat every N seconds …
down()          → DOWN + heartbeat loop stops
```

Built into `ServiceApp` automatically — apps don't create it directly.

```python
from tradingcz.sdk.health import HealthPublisher

health = HealthPublisher(faf, "my-service", interval=300)
await health.initializing()   # INITIALIZING
# ... init / recovery ...
await health.ready()          # READY + heartbeat starts
# ... app runs ...
await health.down()           # DOWN + heartbeat stops
```

## HealthMonitor

Consumes `SERVICE_LIFECYCLE` events from other services via a shared `EventRouter`.
Tracks liveness — marks a service alive on `INITIALIZING`, `READY`, or `HEARTBEAT`.
Two triggers fire the `on_down` callback:
- Explicit `"down"` event (graceful shutdown)
- No lifecycle event for > `ttl` seconds (crash / partition)

```python
from tradingcz.sdk.health import HealthMonitor
from tradingcz.sdk.messaging import EventRouter

router = EventRouter(channel)
monitor = HealthMonitor(router, ttl=600, sweep_interval=60)

async def on_service_down(service_id: str) -> None:
    print(f"Service DOWN: {service_id}")
    # e.g. reassign partitions, alert, etc.

monitor.on_down(on_service_down)
await monitor.start()

# EventRouter dispatches SERVICE_LIFECYCLE events to the monitor:
await router.run()  # blocks until cancelled

await monitor.stop()
```

> **Shares the EventRouter consumer** — no duplicate consumer groups.
> The monitor registers a handler via ``router.on(EventType.SERVICE_LIFECYCLE, ...)``.
