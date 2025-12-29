from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Generic, Self, TypeVar

KeyT = TypeVar("KeyT")
ValueT = TypeVar("ValueT")


class Writer(ABC, Generic[KeyT, ValueT]):
    @abstractmethod
    def write(
        self,
        key: KeyT,
        value: ValueT,
        callback: Callable[[Exception | None, Any], None] | None = None,
    ) -> None:
        """Send a message to the underlying transport."""

    def close(self) -> None:  # pragma: no cover - default no-op
        """Release any held resources."""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()
