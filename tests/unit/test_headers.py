"""Unit tests for tradingcz.models.headers and tradingcz.models.dispatch."""

from tradingcz.models.enums.event import EventType
from tradingcz.models.headers import (
    Header,
    build_event_key,
    make_data_headers,
    make_event_headers,
    make_headers,  # backward-compat alias
)
from tradingcz.models.dispatch import model_for, parse_message


class TestHeaderEnum:
    """Verify Header enum members are StrEnum (usable as dict keys)."""

    def test_all_members_are_strings(self) -> None:
        for member in Header:
            assert isinstance(member, str), f"{member.name} is not a string"
            assert member.value == str(member)

    def test_no_duplicate_values(self) -> None:
        values = [m.value for m in Header]
        assert len(values) == len(set(values)), "Header values must be unique"

    def test_used_as_dict_key(self) -> None:
        d: dict[str, str] = {}
        d[Header.EVENT_TYPE] = "data_request"
        assert d["event_type"] == "data_request"
        assert d[Header.EVENT_TYPE] == "data_request"


class TestEventTypeEnum:
    """Verify EventType enum completeness."""

    def test_all_members_are_strings(self) -> None:
        for member in EventType:
            assert isinstance(member, str), f"{member.name} is not a string"

    def test_no_duplicate_values(self) -> None:
        values = [m.value for m in EventType]
        assert len(values) == len(set(values)), "EventType values must be unique"


class TestMakeEventHeaders:
    """Tests for make_event_headers() — event-topic messages, no sequence."""

    def test_minimal(self) -> None:
        h = make_event_headers(event_type=EventType.DATA_REQUEST)
        assert h[Header.EVENT_TYPE] == "data_request"
        assert h[Header.SOURCE_APP] == ""
        assert Header.SEQUENCE not in h  # no sequence for event headers

    def test_full(self) -> None:
        h = make_event_headers(
            event_type=EventType.DATA_REQUEST,
            source_app="ingestion",
            request_id="abc-123",
            broker="alpaca",
        )
        assert h[Header.EVENT_TYPE] == "data_request"
        assert h[Header.SOURCE_APP] == "ingestion"
        assert h[Header.REQUEST_ID] == "abc-123"
        assert h[Header.BROKER] == "alpaca"

    def test_extra_kwargs(self) -> None:
        h = make_event_headers(event_type=EventType.TRADING_SIGNAL, custom="val")
        assert h["custom"] == "val"

    def test_backward_compat_alias(self) -> None:
        """make_headers is an alias for make_event_headers."""
        h = make_headers(event_type=EventType.DATA_REQUEST)
        assert Header.SEQUENCE not in h


class TestMakeDataHeaders:
    """Tests for make_data_headers() — data-topic messages, includes sequence."""

    def test_minimal(self) -> None:
        h = make_data_headers(event_type=EventType.BAR)
        assert h[Header.EVENT_TYPE] == "bar"
        assert h[Header.SEQUENCE] == "0"

    def test_with_sequence(self) -> None:
        h = make_data_headers(event_type=EventType.BAR, sequence=42)
        assert h[Header.SEQUENCE] == "42"
        assert isinstance(h[Header.SEQUENCE], str)

    def test_extra_kwargs(self) -> None:
        h = make_data_headers(event_type=EventType.TRADE, custom_field="x")
        assert h["custom_field"] == "x"


class TestBuildEventKey:
    """Tests for build_event_key()."""

    def test_basic(self) -> None:
        key = build_event_key(EventType.DATA_REQUEST, "test-app", "abc")
        assert key == "data_request:test-app:abc"


class TestModelFor:
    """Tests for model_for() lookup."""

    def test_known_type(self) -> None:
        from tradingcz.models.events import DataRequest
        assert model_for(EventType.DATA_REQUEST) is DataRequest

    def test_str_accepted(self) -> None:
        from tradingcz.models.events import DataReady
        assert model_for("data_ready") is DataReady

    def test_unknown_raises(self) -> None:
        with __import__("pytest").raises(ValueError):
            model_for("bogus_type")


class TestParseMessage:
    """Tests for parse_message() dispatch."""

    def test_parse_data_request(self) -> None:
        from tradingcz.models.events import DataRequest
        payload = b'{"request_id":"abc","symbols":["AAPL"]}'
        result = parse_message(EventType.DATA_REQUEST, payload)
        assert isinstance(result, DataRequest)
        assert result.request_id == "abc"

    def test_parse_unknown_type_raises(self) -> None:
        try:
            parse_message("bogus", b"{}")
            raise AssertionError("Should have raised ValueError")
        except ValueError:
            pass
