"""Bidirectional key ↔ Pydantic model registry — base class for all model registries.

For detailed docs see :file:`lang/_README.md`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from pydantic import BaseModel


class ModelRegistry[K]:
    """Generic bidirectional key ↔ Pydantic model.

    Subclass with a concrete key type to create a new registry.
    Each subclass gets isolated storage via ``__init_subclass__``.
    All methods are classmethods — no instances needed.
    """

    _by_key: ClassVar[dict[K, type[BaseModel]]]
    _by_model: ClassVar[dict[type[BaseModel], K]]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls._by_key = {}
        cls._by_model = {}

    @classmethod
    def register(cls, key: K, model: type[BaseModel]) -> type[BaseModel]:
        """Register *model* under *key*.  Raises ValueError on conflict."""
        if key in cls._by_key:
            existing = cls._by_key[key].__name__
            if existing != model.__name__:
                raise ValueError(
                    f"{cls.__name__}: {key!r} already registered to "
                    f"{existing}, cannot re-register to {model.__name__}"
                )
        cls._by_key[key] = model
        cls._by_model[model] = key
        return model

    @classmethod
    def model_for(cls, key: K) -> type[BaseModel]:
        """Return the model for *key*, or raise KeyError."""
        try:
            return cls._by_key[key]
        except KeyError:
            raise KeyError(
                f"{cls.__name__}: no model for {key!r}. "
                f"Registered: {list(cls._by_key)}"
            ) from None

    @classmethod
    def key_for(cls, model: type[BaseModel] | BaseModel) -> K | None:
        """Return the key for *model* (class or instance), or None."""
        cls_ = model if isinstance(model, type) else type(model)
        return cls._by_model.get(cls_)

    @classmethod
    def is_registered(cls, model: type[BaseModel] | BaseModel) -> bool:
        """Check whether *model* is registered."""
        cls_ = model if isinstance(model, type) else type(model)
        return cls_ in cls._by_model

    @classmethod
    def as_dict(cls) -> dict[K, type[BaseModel]]:
        """Return a shallow copy for consumers."""
        return dict(cls._by_key)

    @classmethod
    def registered_models(cls) -> Mapping[type[BaseModel], K]:
        """Return a read-only view of all registered models."""
        return cls._by_model


__all__ = ["ModelRegistry"]
