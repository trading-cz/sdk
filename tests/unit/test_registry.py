"""Unit tests for tradingcz.sdk._registry.Registry."""

import pytest
from tradingcz.sdk._registry import Registry


class TestRegistry:
    """Tests for the generic Registry class."""

    def test_register_and_get(self) -> None:
        registry = Registry[str, type]()

        @registry.register("a")
        class Foo:
            pass

        cls, factory = registry.get("a")
        assert cls is Foo
        instance = factory(cls=cls)
        assert isinstance(instance, Foo)

    def test_multiple_keys(self) -> None:
        registry = Registry[str, type]()

        @registry.register("a")
        class Foo:
            pass

        @registry.register("b")
        class Bar:
            pass

        a_cls, _ = registry.get("a")
        b_cls, _ = registry.get("b")
        assert a_cls is Foo
        assert b_cls is Bar

    def test_tuple_key(self) -> None:
        registry = Registry[tuple[str, str], type]()

        @registry.register(("alpaca", "historical"))
        class AlpacaHistorical:
            pass

        @registry.register(("alpaca", "stream"))
        class AlpacaStream:
            pass

        cls1, _ = registry.get(("alpaca", "historical"))
        cls2, _ = registry.get(("alpaca", "stream"))
        assert cls1 is AlpacaHistorical
        assert cls2 is AlpacaStream

    def test_missing_key_raises_keyerror(self) -> None:
        registry = Registry[str, type]()
        with pytest.raises(KeyError):
            registry.get("nonexistent")

    def test_custom_factory(self) -> None:
        registry = Registry[str, type]()

        def my_factory(cls, **kw):
            return cls(x=kw.get("x", 0))

        @registry.register("custom", factory=my_factory)
        class Custom:
            def __init__(self, x: int = 0) -> None:
                self.x = x

        cls, factory = registry.get("custom")
        assert factory is my_factory
        instance = factory(cls=cls, x=42)
        assert instance.x == 42

    def test_default_factory_passes_kwargs(self) -> None:
        registry = Registry[str, type]()

        @registry.register("with-args")
        class WithArgs:
            def __init__(self, name: str = "", value: int = 0) -> None:
                self.name = name
                self.value = value

        cls, factory = registry.get("with-args")
        instance = factory(cls=cls, name="test", value=99)
        assert instance.name == "test"
        assert instance.value == 99

    def test_decorator_returns_class(self) -> None:
        registry = Registry[str, type]()

        @registry.register("returns-self")
        class ReturnsSelf:
            pass

        # The decorator returns the class unchanged
        assert ReturnsSelf.__name__ == "ReturnsSelf"

    def test_overwrite_key(self) -> None:
        """Registering a second class under the same key overwrites."""
        registry = Registry[str, type]()

        @registry.register("same")
        class First:
            pass

        @registry.register("same")
        class Second:
            pass

        cls, _ = registry.get("same")
        assert cls is Second
