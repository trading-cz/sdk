"""Service health monitoring.

Public API:
  - ``HealthMonitor`` — consume lifecycle events from other services
"""

from tradingcz.sdk.health.monitor import HealthMonitor

__all__ = ["HealthMonitor"]
