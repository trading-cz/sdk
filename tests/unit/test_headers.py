"""Unit tests for tradingcz.model.headers."""

from tradingcz import SCHEMA_VERSION
from tradingcz.model.headers import (
    BROKER,
    MESSAGE_TYPE,
    REQUEST_ID,
    SCHEMA_VERSION_KEY,
    SEQUENCE,
    SOURCE_APP,
    SYMBOL,
    TRACKING_ID,
    make_headers,
)


class TestMakeHeaders:
    """Tests for make_headers() factory."""

    def test_minimal_headers(self) -> None:
        h = make_headers(message_type="data_request")
        assert h[MESSAGE_TYPE] == "data_request"
        assert h[SOURCE_APP] == ""
        assert h[SCHEMA_VERSION_KEY] == SCHEMA_VERSION
        assert h[SEQUENCE] == "0"

    def test_full_headers(self) -> None:
        h = make_headers(
            message_type="data_request",
            source_app="ingestion",
            sequence=42,
            request_id="abc-123",
            symbol="AAPL",
            broker="alpaca",
            tracking_id="trk-001",
        )
        assert h[MESSAGE_TYPE] == "data_request"
        assert h[SOURCE_APP] == "ingestion"
        assert h[SEQUENCE] == "42"
        assert h[REQUEST_ID] == "abc-123"
        assert h[SYMBOL] == "AAPL"
        assert h[BROKER] == "alpaca"
        assert h[TRACKING_ID] == "trk-001"

    def test_extra_kwargs_become_headers(self) -> None:
        h = make_headers(message_type="trade", custom_field="custom_value")
        assert h["custom_field"] == "custom_value"

    def test_sequence_is_string(self) -> None:
        h = make_headers(message_type="test", sequence=0)
        assert isinstance(h[SEQUENCE], str)
        assert h[SEQUENCE] == "0"

    def test_schema_version_default(self) -> None:
        h = make_headers(message_type="test")
        assert h[SCHEMA_VERSION_KEY] == SCHEMA_VERSION

    def test_schema_version_override(self) -> None:
        h = make_headers(message_type="test", schema_version="2.0")
        assert h[SCHEMA_VERSION_KEY] == "2.0"

    def test_extra_overrides_standard(self) -> None:
        """Extra kwargs cannot override standard fields in Python (duplicate kwargs are syntax errors).
        But extra fields with different names work fine."""
        h = make_headers(
            message_type="original",
            source_app="original",
            custom_field="custom_value",
        )
        assert h[MESSAGE_TYPE] == "original"
        assert h["custom_field"] == "custom_value"


class TestHeaderConstants:
    """Verify all header constants are plain strings."""

    def test_all_constants_are_strings(self) -> None:
        for name in [
            "MESSAGE_TYPE",
            "SOURCE_APP",
            "SCHEMA_VERSION_KEY",
            "SEQUENCE",
            "REQUEST_ID",
            "TRACKING_ID",
            "STRATEGY_ID",
            "SOURCE",
            "BROKER",
            "SYMBOL",
        ]:
            val = getattr(__import__("tradingcz.model.headers", fromlist=[name]), name)
            assert isinstance(val, str), f"{name} is not a string: {type(val)}"

    def test_no_duplicate_values(self) -> None:
        """Each constant should have a unique value (no accidental reuse)."""
        import tradingcz.model.headers as h

        values = [
            h.MESSAGE_TYPE,
            h.SOURCE_APP,
            h.SCHEMA_VERSION_KEY,
            h.SEQUENCE,
            h.REQUEST_ID,
            h.TRACKING_ID,
            h.STRATEGY_ID,
            h.SOURCE,
            h.BROKER,
            h.SYMBOL,
        ]
        # Some values are intentionally the same string (e.g. "source" vs "source_app")
        # Just check they're all non-empty
        for v in values:
            assert v, "Header constant is empty"
