# health — Service Health Monitoring

Track liveness of other services. Registers on a shared `EventRouter` — no separate Kafka consumer.

## HealthMonitor

Consumes `SERVICE_LIFECYCLE` events from other services via a shared `EventRouter`.
Two triggers fire the `on_down` callback:
- Explicit `"down"` event (graceful shutdown)
- No heartbeat for > `ttl` seconds (crash / partition)

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
> The monitor registers a handler via `router.on(EventType.SERVICE_LIFECYCLE, ...)`.
