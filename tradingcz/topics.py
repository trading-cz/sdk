"""Topic registry — single source of truth for Kafka topic names and configs.

Replaces the previously lost ``tradingcz.kafka.Topics`` and ``tradingcz.kafka.keys``
modules.  Provides hyphen-separated, K8s-safe, environment-scoped topic names
(e.g. ``dev-event``, ``dev-market-data``).

Usage (in any service)::

    from tradingcz.topics import TopicConfig, TopicRegistry

    topics = TopicRegistry(env="dev")
    channel = await transport.channel(topics.market_data.name)

    # Partition key for symbol-grouped data:
    key = TopicRegistry.partition_key("ingestion", "AAPL")
"""

from dataclasses import dataclass, field


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
    replication_factor: int = 1
    retention_ms: int = 432_000_000  # 5 days
    cleanup_policy: str = "delete"


class TopicRegistry:
    """Central topic naming and configuration.

    Instantiate once per process with the target environment.
    Topic names are environment-scoped for security isolation
    (``dev-market-data`` and ``prd-market-data`` are separate topics).

    Example::

        registry = TopicRegistry(env=\"dev\")
        assert registry.market_data.name == \"dev-market-data\"
        assert registry.events.name == \"dev-event\"
    """

    def __init__(self, env: str = "dev") -> None:
        # Hyphen-separated naming: <env>-<topic> (K8s-safe, no dots or underscores)

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

        self.signals = TopicConfig(name=f"{env}-raw-signal", partitions=5)
        self.execution_requests = TopicConfig(name=f"{env}-execution-request", partitions=5)
        self.execution_responses = TopicConfig(name=f"{env}-execution-response", partitions=5)
        self.positions = TopicConfig(name=f"{env}-position-events", partitions=3)

    def historical(self, request_id: str) -> str:
        """Return ephemeral topic name for a historical data request.

        Example: ``\"dev-market-data-historical-abc123\"``
        """
        return f"{self.market_data.name}-historical-{request_id}"

    # ------------------------------------------------------------------
    # Partition key helpers
    # ------------------------------------------------------------------

    @staticmethod
    def partition_key(source: str, symbol: str) -> str:
        """Deterministic partition key for symbol-grouped data.

        Co-locates all messages for a given (source, symbol) pair on
        the same Kafka partition, preserving order within that partition.

        Args:
            source: Origin service name (e.g. ``"ingestion"``).
            symbol: Ticker symbol (e.g. ``"AAPL"``).

        Returns:
            A string key suitable for Kafka message keys.

        Example::

            key = TopicRegistry.partition_key("ingestion", "AAPL")
            # key == "ingestion:AAPL"
        """
        return f"{source}:{symbol}"

    @staticmethod
    def signal_key(strategy_id: str, symbol: str) -> str:
        """Partition key for trading signals.

        Args:
            strategy_id: Strategy identifier (e.g. ``"pcb_breakout"``).
            symbol: Ticker symbol.

        Returns:
            Key string like ``"pcb_breakout:AAPL"``.
        """
        return f"{strategy_id}:{symbol}"
