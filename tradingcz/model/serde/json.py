"""JSON serialization for domain models.

Design:
- SDK owns domain serialization (JSON/CSV) because it is provider-agnostic.
- Domain dataclasses can remain lightweight; serde functions live here.
- We deliberately do NOT rely on `__dict__` (important for `slots=True`).
"""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import datetime
from typing import Any, TypeVar, get_args, get_origin, get_type_hints

from tradingcz.model.domain.bar import Bar
from tradingcz.model.domain.quote import Quote
from tradingcz.model.domain.snapshot import Snapshot
from tradingcz.model.domain.trade import Trade

T = TypeVar("T")


def _serialize_value(value: Any) -> Any:
    """Recursively serialize a value, handling datetime and nested dataclasses."""
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        # Nested dataclass: recurse
        return _model_to_dict(value)
    return value


def _model_to_dict(obj: Any) -> dict[str, Any]:
    """Generic serialization: convert any dataclass to dict."""
    result: dict[str, Any] = {}
    for field in fields(obj):
        value = getattr(obj, field.name)
        if value is None:
            result[field.name] = None
        else:
            result[field.name] = _serialize_value(value)
    return result


def _deserialize_value(field_type: Any, value: Any) -> Any:  # pylint: disable=R0911
    """Deserialize a value based on its field type annotation."""
    if value is None:
        return None
    # Handle datetime
    if field_type is datetime:
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return value
    # Handle Union types (e.g., Quote | None)
    origin = get_origin(field_type)
    if origin is not None:
        args = get_args(field_type)
        # For Union, try each type except NoneType
        for arg in args:
            if isinstance(arg, type) and issubclass(arg, type(None)):
                continue
            if is_dataclass(arg):
                if isinstance(value, dict):
                    return _model_from_dict(arg, value)
        return value
    # Handle nested dataclasses
    try:
        if is_dataclass(field_type):
            if isinstance(value, dict):
                return _model_from_dict(field_type, value)
            return value
    except TypeError:
        pass
    # Basic types: int, float, str, bool, list, etc. - return as-is
    return value


def _model_from_dict(cls: type[T], data: dict[str, Any]) -> T:  # noqa: UP047
    """Generic deserialization: convert dict to dataclass using field types."""
    kwargs: dict[str, Any] = {}
    # Use get_type_hints to resolve stringified annotations
    hints = get_type_hints(cls)
    for field in fields(cls):
        if field.name not in data:
            continue
        value = data[field.name]
        if value is None:
            kwargs[field.name] = None
        else:
            # Use type hints (resolved) instead of field.type (stringified)
            field_type = hints.get(field.name, field.type)
            kwargs[field.name] = _deserialize_value(field_type, value)
    return cls(**kwargs)


def bar_to_dict(bar: Bar) -> dict[str, Any]:  # pylint: disable=C0104
    return _model_to_dict(bar)


def bar_from_dict(data: dict[str, Any]) -> Bar:  # pylint: disable=C0104
    return _model_from_dict(Bar, data)


def bar_to_json(bar: Bar) -> str:  # pylint: disable=C0104
    return json.dumps(bar_to_dict(bar), ensure_ascii=False)


def bar_from_json(payload: str) -> Bar:
    return bar_from_dict(json.loads(payload))


def quote_to_dict(quote: Quote) -> dict[str, Any]:
    return _model_to_dict(quote)


def quote_from_dict(data: dict[str, Any]) -> Quote:
    return _model_from_dict(Quote, data)


def quote_to_json(quote: Quote) -> str:
    return json.dumps(quote_to_dict(quote), ensure_ascii=False)


def quote_from_json(payload: str) -> Quote:
    return quote_from_dict(json.loads(payload))


def trade_to_dict(trade: Trade) -> dict[str, Any]:
    return _model_to_dict(trade)


def trade_from_dict(data: dict[str, Any]) -> Trade:
    return _model_from_dict(Trade, data)


def trade_to_json(trade: Trade) -> str:
    return json.dumps(trade_to_dict(trade), ensure_ascii=False)


def trade_from_json(payload: str) -> Trade:
    return trade_from_dict(json.loads(payload))


def snapshot_to_dict(snapshot: Snapshot) -> dict[str, Any]:
    return _model_to_dict(snapshot)


def snapshot_from_dict(data: dict[str, Any]) -> Snapshot:
    return _model_from_dict(Snapshot, data)


def snapshot_to_json(snapshot: Snapshot) -> str:
    return json.dumps(snapshot_to_dict(snapshot), ensure_ascii=False)


def snapshot_from_json(payload: str) -> Snapshot:
    return snapshot_from_dict(json.loads(payload))
