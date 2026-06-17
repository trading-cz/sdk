"""Health/lifecycle event model.

Every service using the SDK emits lifecycle events on the shared event
topic so the platform can track which services are running, detect
crashes, and trigger cleanup actions (e.g., ingestion removes streaming
subscriptions for services that went down).

Event types:
  - ``"up"``         — emitted once on ``TradingApp.start()``
  - ``"heartbeat"``  — emitted periodically (default every 5 minutes)
  - ``"down"``       — emitted on ``TradingApp.close()`` (graceful shutdown)
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class LifecycleEvent(BaseModel):
    # service_id: str -> bude v header
    # TODO enum
    type: Literal["up", "heartbeat", "down"]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))