"""Lazy[T] — descriptor for lazy-initialized attributes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class Lazy[T]:
    """Descriptor that initializes its value on first attribute access."""

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
