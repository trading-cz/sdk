"""Decorator-based factory registry — key → (class, factory)."""

from collections.abc import Callable
from typing import Any, cast


class FactoryRegistry[K, V]:
    """Map keys to (class, factory) pairs.  Default factory calls ``cls(**deps)``."""

    _default_factory: Callable[..., Any] = staticmethod(lambda cls, **kw: cls(**kw))

    def __init__(self) -> None:
        self._items: dict[K, tuple[V, Callable[..., Any]]] = {}

    def register(self, key: K, *, factory: Callable[..., Any] | None = None) -> Callable[[type], type]:
        """Decorator: register the decorated class under *key*."""
        def decorator(cls: type) -> type:
            self._items[key] = (cast(V, cls), factory or self._default_factory)
            return cls

        return decorator

    def get(self, key: K) -> tuple[V, Callable[..., Any]]:
        """Return (class, factory) for *key*, or raise KeyError."""
        return self._items[key]


__all__ = ["FactoryRegistry"]
