"""Transport protocol — abstract channel and transport interfaces.

Layer 0: moves bytes through named channels.
No knowledge of events, models, or serialization.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Message:
    """A received message — raw payload with optional key."""

    payload: bytes
    key: str = ""


class Channel(ABC):
    """Named byte-pipe. Maps to one Kafka topic.

    ``send()`` publishes a message.
    ``receive()`` yields messages — each call creates an independent
    subscriber (fan-out within a single process).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Logical channel name (maps to Kafka topic)."""

    @abstractmethod
    async def send(self, payload: bytes, *, key: str = "") -> None:
        """Publish *payload* with optional *key* to the channel."""

    @abstractmethod
    async def receive(self) -> AsyncIterator[Message]:
        """Yield messages from this channel.

        Each call returns an independent async generator — multiple consumers
        each see every message (in-process fan-out).
        """
        # async generator stub — subclasses must yield
        return
        yield  # pragma: no cover  # noqa: unreachable

    @abstractmethod
    async def close(self) -> None:
        """Release resources held by this channel."""


class Transport(ABC):
    """Channel factory — caches channels by name.

    ``channel("events")`` always returns the same Channel instance.
    This ensures one Kafka consumer per topic per process.
    """

    @abstractmethod
    async def channel(self, name: str) -> Channel:
        """Return (or create) the channel for *name*."""

    @abstractmethod
    async def close(self) -> None:
        """Close all channels and release transport resources."""
