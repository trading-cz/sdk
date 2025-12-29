from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Generic, Self, TypeVar

KeyT = TypeVar("KeyT")
ValueT = TypeVar("ValueT")


class Reader(ABC, Generic[KeyT, ValueT]):
    @abstractmethod
    def read(self, callback: Callable[[KeyT, ValueT], None]) -> None:
        """Start the read loop and invoke the callback for each message."""

    def close(self) -> None:  # pragma: no cover - default no-op
        """Release any held resources."""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()
