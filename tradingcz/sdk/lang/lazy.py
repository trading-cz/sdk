"""Lazy[T] — descriptor for lazy-initialized attributes.

Usage::

    class TransportProducer:
        _producer = Lazy(lambda self: SyncProducer(self._settings.producer_config()))

        def send(self, name, payload):
            producer = self._producer  # initialized on first access
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class Lazy[T]:
    """Descriptor that initializes its value on first attribute access.

    The factory receives ``self`` (the owning instance) and returns the value.
    Once set, the value is stored in the instance __dict__ — further accesses
    bypass the descriptor entirely.
    """

    def __init__(self, factory: Callable[[Any], T]) -> None:
        self._factory = factory
        self._name: str = ""  # set by __set_name__

    def __set_name__(self, owner: type, name: str) -> None:
        self._name = name

    def __get__(self, obj: object | None, owner: type) -> T:
        if obj is None:
            return self  # type: ignore[return-value]
        value = self._factory(obj)
        obj.__dict__[self._name] = value
        return value


__all__ = ["Lazy"]
