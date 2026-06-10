"""Generic class registry — decorator-based self-registration.

Classes declare what key they serve via a decorator.  The registry maps
key → (class, factory_function) and supports custom factory callables.

Usage::

    adapters = Registry[str, type]()

    @adapters.register("alpaca")
    class AlpacaAdapter:
        ...

    cls, factory = adapters.get("alpaca")
    instance = factory(cls=cls, api_key="...")
"""

from collections.abc import Callable
from typing import Any


class Registry[K, V]:
    """Decorator-based registry mapping keys to (class, factory) pairs.

    The *factory* is called with ``(cls, **deps)`` and returns an instance.
    The default factory just calls ``cls(**deps)`` — handlers accept all
    kwargs and ignore extra ones via ``**kwargs`` in their constructor.

    Type parameters:
        ``K``: Registry key type (e.g. ``str``, ``tuple[str, str]``).
        ``V``: Registered value type (almost always ``type``).
    """

    _default_factory: Callable[..., Any] = staticmethod(lambda cls, **kw: cls(**kw))

    def __init__(self) -> None:
        self._items: dict[K, tuple[V, Callable[..., Any]]] = {}

    def register(
        self, key: K, *, factory: Callable[..., Any] | None = None,
    ) -> Callable[[type], type]:
        """Decorator: register the decorated class under *key*.

        Args:
            key: Lookup key (e.g. ``"alpaca"`` or ``("alpaca", "historical")``).
            factory: Optional callable ``(cls, **deps) -> instance``.
                     Default: calls ``cls(**deps)``.
        """
        def decorator(cls: type) -> type:
            self._items[key] = (cls, factory or self._default_factory)
            return cls
        return decorator

    def get(self, key: K) -> tuple[V, Callable[..., Any]]:
        """Return (class, factory) for *key*, or raise KeyError."""
        return self._items[key]


__all__ = ["Registry"]
