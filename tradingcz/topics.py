"""Topic registry — single source of truth for Kafka topic names and configs.

Replaces the previously lost ``tradingcz.kafka.Topics`` and ``tradingcz.kafka.keys``
modules.  Provides hyphen-separated, K8s-safe, environment-scoped topic names
(e.g. ``dev-event``, ``dev-market-data``).

Topic names are environment-scoped for security isolation
(``dev-market-data`` and ``prd-market-data`` are separate topics).

JSON Key helpers produce Pydantic-serialized JSON keys for each topic type.
All message keys MUST be JSON — never plain strings — for consistent tooling
and schema validation.

Usage (in any service)::

    from tradingcz.topics import TopicConfig, TopicRegistry

    topics = TopicRegistry(env="dev")
    channel = await transport.channel(topics.market_data.name)

    # Market-data JSON key (NOT a plain string):
    key = topics.market_data_key("ingestion", "alpaca", "AAPL")
    # → '{"source":"ingestion","broker":"alpaca","symbol":"AAPL","ts":"...",}'
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
    # JSON key generators — one per topic type
    # ------------------------------------------------------------------

    @staticmethod
    def control_plane_key(
        event_type: str,
        source: str,
        request_id: str,
    ) -> str:
        """JSON key for control-plane messages on the events topic.

        Used for DataRequest, DataReady, and DataError messages.

        Args:
            event_type: ``"data_request"``, ``"data_ready"``, or ``"data_error"``.
            source: App identifier (e.g. ``"smoke_test"``, ``"ingestion"``).
            request_id: Correlation ID linking request to response.

        Returns:
            JSON string like ``'{"event_type":"data_request","source":"smoke_test",...}'``.

        Example::

            key = TopicRegistry.control_plane_key(
                "data_request", "smoke_test", request_id,
            )
        """
        from tradingcz.model.kafka_key import ControlPlaneKey  # pylint: disable=import-outside-toplevel

        return ControlPlaneKey(
            event_type=event_type,
            source=source,
            request_id=request_id,
        ).model_dump_json()

    @staticmethod
    def market_data_key(
        source: str,
        broker: str,
        symbol: str,
    ) -> str:
        """JSON key for market-data messages (Trade, Quote, Bar).

        Co-locates all data for a given (broker, symbol) pair on the same
        Kafka partition.

        Args:
            source: Origin service (e.g. ``"ingestion"``).
            broker: Broker identifier (e.g. ``"alpaca"``).
            symbol: Ticker symbol (e.g. ``"AAPL"``).

        Returns:
            JSON string like ``'{"source":"ingestion","broker":"alpaca","symbol":"AAPL",...}'``.

        Example::

            key = TopicRegistry.market_data_key("ingestion", "alpaca", "AAPL")
        """
        from tradingcz.model.kafka_key import MarketDataKey  # pylint: disable=import-outside-toplevel

        return MarketDataKey(
            source=source,
            broker=broker,
            symbol=symbol,
        ).model_dump_json()
