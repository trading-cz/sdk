"""Topic registry — environment-scoped Kafka topic names (e.g. dev-event)."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TopicConfig:
    """Immutable topic configuration."""

    name: str
    partitions: int = 5
    replication_factor: int = 2
    retention_ms: int = 259_200_000  # 3 days
    cleanup_policy: str = "delete"


class TopicRegistry:
    """Central topic naming, scoped by environment.

    Usage::

        topics = TopicRegistry(env=\"dev\")
        channel = await transport.channel(topics.market_data.name)
    """

    def __init__(self, env: str = "dev") -> None:
        self.events = TopicConfig(name=f"{env}-event", partitions=1)
        self.market_data = TopicConfig(name=f"{env}-stock-market-stream-data", partitions=5)
        self.historical_data = TopicConfig(name=f"{env}-stock-market-historical-data", partitions=1)
