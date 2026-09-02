"""Concrete model registries and decorators for wire-protocol dispatch.

* :class:`EventRegistry` — ``EventType`` ↔ Pydantic model (Kafka header dispatch)
* :class:`MarketDataRegistry` — ``MarketDataType`` ↔ Pydantic model (stream topic routing)

For the generic base class see :class:`tradingcz.sdk.lang.model_registry.ModelRegistry`.
For runtime factory dispatch see :class:`tradingcz.sdk.lang.registry.FactoryRegistry`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel

from tradingcz.sdk.exceptions import RegistryError
from tradingcz.sdk.lang.model_registry import ModelRegistry

# TYPE_CHECKING-only: these are only used in type annotations (decorator
# signatures, return types, ClassVar parameterisation).  `from __future__
# import annotations` makes all annotations strings at runtime, so the
# symbols are never needed at import time.  Keeping them runtime would
# create a circular import: registry → models.enums.event → models.__init__
# → models.events.* (all of which import register_event from here).
if TYPE_CHECKING:
    from tradingcz.sdk.models.enums.event import EventType, MarketDataType

# ═══════════════════════════════════════════════════════════════════════
# EventRegistry — wire-protocol dispatch
# ═══════════════════════════════════════════════════════════════════════

ModelT = TypeVar("ModelT", bound=BaseModel)

class EventRegistry(ModelRegistry["EventType"]):
    """EventType ↔ Pydantic model.

    Every model that travels over Kafka with an ``event_type`` header
    must be registered here.  Used by TypedConsumer / EventRouter.
    """

    @classmethod
    def event_type_for(cls, model: type[BaseModel] | BaseModel) -> EventType:
        """Return the EventType for *model*, or raise RegistryError."""
        result = cls.key_for(model)
        if result is None:
            cls_ = model if isinstance(model, type) else type(model)
            raise RegistryError(
                f"Model {cls_.__name__} is not registered in EventRegistry. "
                f"Add @register_event(EventType.XXX) to the class."
            )
        return result

    @classmethod
    def as_types_dict(cls) -> dict[EventType, type[BaseModel]]:
        """Alias for :meth:`as_dict`."""
        return cls.as_dict()


class MarketDataRegistry(ModelRegistry["MarketDataType"]):
    """MarketDataType ↔ Pydantic model.

    Only market-data models (Bar, Quote, Trade, etc.) are registered here.
    Used by streaming pipelines for per-type topic routing.
    """

    @classmethod
    def data_type_for(cls, model: type[BaseModel] | BaseModel) -> MarketDataType:
        """Return the MarketDataType for *model*, or raise RegistryError."""
        result = cls.key_for(model)
        if result is None:
            cls_ = model if isinstance(model, type) else type(model)
            raise RegistryError(
                f"Model {cls_.__name__} is not registered in MarketDataRegistry. "
                f"Add @register_market_data(MarketDataType.XXX) to the class."
            )
        return result


# ═══════════════════════════════════════════════════════════════════════
# Decorators
# ═══════════════════════════════════════════════════════════════════════


def register_event(event_type: EventType) -> Callable[[type[ModelT]], type[ModelT]]:
    """Decorator: register a model under an EventType.

        @register_event(EventType.BAR)
        class Bar(BaseModel): ...
    """
    def decorator(cls: type[ModelT]) -> type[ModelT]:
        EventRegistry.register(event_type, cls)
        return cls
    return decorator


def register_market_data(data_type: MarketDataType) -> Callable[[type[ModelT]], type[ModelT]]:
    """Decorator: register a model under a MarketDataType.

        @register_market_data(MarketDataType.BARS)
        class Bar(BaseModel): ...
    """
    def decorator(cls: type[ModelT]) -> type[ModelT]:
        MarketDataRegistry.register(data_type, cls)
        return cls
    return decorator


__all__ = [
    "EventRegistry",
    "MarketDataRegistry",
    "register_event",
    "register_market_data",
]
