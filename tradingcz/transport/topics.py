"""Topic registry — single source of truth for Kafka topic names and configs.

Provides hyphen-separated, K8s-safe, environment-scoped topic names
(e.g. ``dev-event``, ``dev-market-data``).

Topic names are environment-scoped for security isolation
(``dev-market-data`` and ``prd-market-data`` are separate topics).

Message keys are plain strings (e.g. ``"AAPL"``) for partition routing.
Metadata lives in headers via ``tradingcz.model.headers.make_headers()``.

Usage (in any service)::

    from tradingcz.transport import TopicRegistry

    topics = TopicRegistry(env="dev")
    channel = await transport.channel(topics.market_data.name)
    await channel.send(payload, key="AAPL", headers=make_headers(...))
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TopicConfig:
    """Immutable topic configuration.

    Attributes:
        name: Kafka topic name (e.g. ``"dev-market-data"``).
        partitions: Default partition count for auto-creation.
        replication_factor: Default replication factor.
        retention_ms: Retention in milliseconds (default 5 days).
        cleanup_policy: ``"delete"`` or ``"compact"``.
    """

    name: str
    partitions: int = 5
    replication_factor: int = 2
    retention_ms: int = 432_000_000  # 5 days
    cleanup_policy: str = "delete"


class TopicRegistry:
    """Central topic naming and configuration.

    Instantiate once per process with the target environment.
    Topic names are environment-scoped for security isolation.

    Example::

        registry = TopicRegistry(env=\"dev\")
        assert registry.market_data.name == \"dev-market-data\"
        assert registry.events.name == \"dev-event\"
    """

    def __init__(self, env: str = "dev") -> None:
        # Control plane: single partition ensures total ordering of
        # DataRequest/DataReady/DataError messages.
        self.events = TopicConfig(name=f"{env}-event", partitions=1)

        # Market data: 5 partitions, keyed by symbol for independent
        # consumption by multiple strategies.
        self.market_data = TopicConfig(
            name=f"{env}-market-data",
            partitions=5,
            retention_ms=86_400_000,  # 1 day for live data
        )

        self.signals = TopicConfig(name=f"{env}-raw-signal", partitions=1)
        self.execution_requests = TopicConfig(name=f"{env}-execution-request", partitions=1)
        self.execution_responses = TopicConfig(name=f"{env}-execution-response", partitions=1)
        self.positions = TopicConfig(name=f"{env}-position-events", partitions=1)

    def historical(self, request_id: str) -> str:
        """Return ephemeral topic name for a historical data request.

        Example: ``\"dev-market-data-historical-abc123\"``
        """
        return f"{self.market_data.name}-historical-{request_id}"
