"""Health/lifecycle event model.

Every service using the SDK emits lifecycle events on the shared event
topic so the platform can track which services are running, detect
crashes, and trigger cleanup actions (e.g., ingestion removes streaming
subscriptions for services that went down).

Lifecycle sequence (managed by ``HealthPublisher`` via ``ServiceApp``)::

    INITIALIZING → READY → HEARTBEAT (periodic, default 5 min) → DOWN

- ``"initializing"`` — emitted early in ``ServiceApp.start()``
- ``"ready"``       — emitted after all init is complete, heartbeat begins
- ``"heartbeat"``   — periodic liveness signal
- ``"down"``        — emitted on ``ServiceApp.close()`` (graceful shutdown)
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from tradingcz.sdk.models.enums.event import LifecycleEventType


class LifecycleEvent(BaseModel):
    """Service health and lifecycle event.

    Emitted by services to signal they are up, running (heartbeat),
    or shutting down. Used by HealthMonitor to track service liveness.
    """

    service_id: str = Field(..., description="Unique identifier for the service instance")
    event: LifecycleEventType = Field(..., description="Lifecycle event type (up, heartbeat, down)")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Event timestamp")