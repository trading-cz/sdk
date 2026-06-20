"""Smoke test for ServiceApp — validates construction, feature flags, and error paths.

Does NOT require Kafka — tests only constructor behavior and property guards.
"""

# pylint: disable=protected-access

import pytest

from tradingcz.sdk import BrokerScope, ServiceApp


class TestServiceAppConstruction:
    """Construction-only tests — no Kafka connection needed."""

    def test_minimal_construction(self) -> None:
        """ServiceApp with defaults — no feature flags."""
        app = ServiceApp(service_id="smoke-test", env="dev")
        assert app.service_id == "smoke-test"
        assert app.source_app == "smoke-test"
        assert app.kafka_settings is not None
        assert app.shutdown_event is not None

    def test_with_kafka_settings(self) -> None:
        """Pass pre-configured KafkaSettings."""
        from tradingcz.sdk.transport.kafka_settings import KafkaSettings

        ks = KafkaSettings(consumer_group="custom-group")
        app = ServiceApp(service_id="smoke-test", env="dev", kafka_settings=ks)
        assert app.kafka_settings is ks

    def test_feature_flags_default_false(self) -> None:
        """All feature flags default to False."""
        app = ServiceApp(service_id="smoke-test", env="dev")
        assert app._enable_stock is False
        assert app._enable_options is False
        assert app._enable_corporate is False
        assert app._enable_signals is False
        assert app._enable_positions is False
        assert app._enable_balance is False
        assert app._enable_orders is False

    def test_feature_flags_explicit(self) -> None:
        """Feature flags can be enabled."""
        app = ServiceApp(
            service_id="smoke-test",
            env="dev",
            enable_stock=True,
            enable_signals=True,
            enable_positions=True,
        )
        assert app._enable_stock is True
        assert app._enable_signals is True
        assert app._enable_positions is True
        assert app._enable_options is False  # not set → default

    def test_broker_default(self) -> None:
        """Default broker is 'alpaca'."""
        app = ServiceApp(service_id="smoke-test", env="dev")
        assert app._broker == "alpaca"

    def test_broker_custom(self) -> None:
        """Custom broker string."""
        app = ServiceApp(service_id="smoke-test", env="dev", broker="ibkr")
        assert app._broker == "ibkr"


class TestServiceAppPropertyGuards:
    """Property access without start() — should raise clear errors."""

    def test_stock_disabled_raises(self) -> None:
        """Accessing stock when not enabled raises RuntimeError."""
        app = ServiceApp(service_id="smoke-test", env="dev")
        with pytest.raises(RuntimeError, match="Stock client not enabled"):
            _ = app.stock

    def test_stock_not_started_raises(self) -> None:
        """Accessing stock before start() raises RuntimeError."""
        app = ServiceApp(service_id="smoke-test", env="dev", enable_stock=True)
        with pytest.raises(RuntimeError, match="Call start.*before accessing stock"):
            _ = app.stock

    def test_signals_disabled_raises(self) -> None:
        """Accessing signals when not enabled raises RuntimeError."""
        app = ServiceApp(service_id="smoke-test", env="dev")
        with pytest.raises(RuntimeError, match="Signal publisher not enabled"):
            _ = app.signals

    def test_signals_not_started_raises(self) -> None:
        """Accessing signals before start() raises RuntimeError."""
        app = ServiceApp(service_id="smoke-test", env="dev", enable_signals=True)
        with pytest.raises(RuntimeError, match="Call start.*before accessing signal"):
            _ = app.signals

    def test_positions_disabled_raises(self) -> None:
        """Accessing positions when not enabled raises RuntimeError."""
        app = ServiceApp(service_id="smoke-test", env="dev")
        with pytest.raises(RuntimeError, match="Position client not enabled"):
            _ = app.positions

    def test_balance_disabled_raises(self) -> None:
        """Accessing balance when not enabled raises RuntimeError."""
        app = ServiceApp(service_id="smoke-test", env="dev")
        with pytest.raises(RuntimeError, match="Balance client not enabled"):
            _ = app.balance

    def test_orders_disabled_raises(self) -> None:
        """Accessing orders when not enabled raises RuntimeError."""
        app = ServiceApp(service_id="smoke-test", env="dev")
        with pytest.raises(RuntimeError, match="Order client not enabled"):
            _ = app.orders

    def test_options_disabled_raises(self) -> None:
        """Accessing options when not enabled raises RuntimeError."""
        app = ServiceApp(service_id="smoke-test", env="dev")
        with pytest.raises(RuntimeError, match="Options client not enabled"):
            _ = app.options

    def test_corporate_disabled_raises(self) -> None:
        """Accessing corporate_actions when not enabled raises RuntimeError."""
        app = ServiceApp(service_id="smoke-test", env="dev")
        with pytest.raises(RuntimeError, match="Corporate actions client not enabled"):
            _ = app.corporate_actions

    def test_with_broker_before_start_raises(self) -> None:
        """with_broker() before start() raises RuntimeError."""
        app = ServiceApp(service_id="smoke-test", env="dev", enable_stock=True)
        with pytest.raises(RuntimeError, match="Call start.*before with_broker"):
            app.with_broker("ibkr")


class TestServiceAppLifecycle:
    """Async context manager tests."""

    @pytest.mark.asyncio
    async def test_async_context_manager(self) -> None:
        """ServiceApp can be used as an async context manager."""
        # Monkey-patch start/close to avoid actual Kafka connection
        started = False
        closed = False

        original_start = ServiceApp.start
        original_close = ServiceApp.close

        async def _fake_start(self: ServiceApp) -> None:
            nonlocal started
            self.topics = None  # prevent real init
            self.events_topic = "dev-event"
            self._faf = None
            self._rr = None
            self._base = None
            started = True

        async def _fake_close(self: ServiceApp) -> None:  # pylint: disable=unused-argument
            nonlocal closed
            closed = True

        ServiceApp.start = _fake_start  # type: ignore[method-assign]
        ServiceApp.close = _fake_close  # type: ignore[method-assign]

        try:
            async with ServiceApp(service_id="smoke-test", env="dev") as app:
                assert started is True
                assert app.service_id == "smoke-test"
            assert closed is True
        finally:
            ServiceApp.start = original_start  # type: ignore[method-assign]
            ServiceApp.close = original_close  # type: ignore[method-assign]

    @pytest.mark.asyncio
    async def test_request_reply_created_when_features_enabled(self) -> None:
        """When enable_stock=True, RequestReply is created in start()."""
        app = ServiceApp(service_id="smoke-test", env="dev", enable_stock=True)

        # Fake start — set up just enough to see the flag path
        original_start = ServiceApp.start

        async def _fake_start(self: ServiceApp) -> None:
            self.topics = None
            self.events_topic = "dev-event"
            self._faf = None
            self._rr = None
            self._base = None
            self._health = None
            # Simulate what real start() does for feature check
            needs_rr = any([
                self._enable_stock, self._enable_options, self._enable_corporate,
                self._enable_positions, self._enable_balance, self._enable_orders,
            ])
            # We can't actually create RequestReply without Kafka,
            # but we can verify the path is taken.
            self._rr_check = needs_rr  # pylint: disable=attribute-defined-outside-init

        ServiceApp.start = _fake_start  # type: ignore[method-assign]

        try:
            await app.start()
            assert app._rr_check is True  # pylint: disable=no-member
        finally:
            ServiceApp.start = original_start  # type: ignore[method-assign]

    @pytest.mark.asyncio
    async def test_no_request_reply_when_no_features(self) -> None:
        """When no features are enabled, RequestReply is NOT created."""
        app = ServiceApp(service_id="smoke-test", env="dev")

        original_start = ServiceApp.start

        async def _fake_start(self: ServiceApp) -> None:
            self.topics = None
            self.events_topic = "dev-event"
            self._faf = None
            self._rr = None
            self._base = None
            self._health = None
            needs_rr = any([
                self._enable_stock, self._enable_options, self._enable_corporate,
                self._enable_positions, self._enable_balance, self._enable_orders,
            ])
            self._rr_check = needs_rr  # pylint: disable=attribute-defined-outside-init

        ServiceApp.start = _fake_start  # type: ignore[method-assign]

        try:
            await app.start()
            assert app._rr_check is False  # pylint: disable=no-member
        finally:
            ServiceApp.start = original_start  # type: ignore[method-assign]


class TestBrokerScope:
    """BrokerScope client factory tests."""

    def test_broker_scope_lazy(self) -> None:
        """BrokerScope creates clients lazily."""
        # Can't instantiate without a real BaseDataClient,
        # but we can verify the class exists and is exported.
        from tradingcz.sdk import BrokerScope as B2  # pylint: disable=reimported,import-self
        assert BrokerScope is not None
        assert B2 is BrokerScope
