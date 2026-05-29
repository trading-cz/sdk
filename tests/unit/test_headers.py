"""Unit tests for tradingcz.model.headers."""

from tradingcz import SCHEMA_VERSION
from tradingcz.model.headers import (
    Header,
    MessageType,
    make_headers,
    message_model,
    parse_message,
)


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
        d[Header.MESSAGE_TYPE] = "data_request"
        assert d["message_type"] == "data_request"
        assert d[Header.MESSAGE_TYPE] == "data_request"


class TestMessageTypeEnum:
    """Verify MessageType enum completeness."""

    def test_all_members_are_strings(self) -> None:
        for member in MessageType:
            assert isinstance(member, str), f"{member.name} is not a string"

    def test_no_duplicate_values(self) -> None:
        values = [m.value for m in MessageType]
        assert len(values) == len(set(values)), "MessageType values must be unique"


class TestMakeHeaders:
    """Tests for make_headers() factory."""

    def test_minimal_headers(self) -> None:
        h = make_headers(message_type=MessageType.DATA_REQUEST)
        assert h[Header.MESSAGE_TYPE] == "data_request"
        assert h[Header.SOURCE_APP] == ""
        assert h[Header.SCHEMA_VERSION] == SCHEMA_VERSION
        assert h[Header.SEQUENCE] == "0"

    def test_with_message_type_enum(self) -> None:
        h = make_headers(message_type=MessageType.DATA_REQUEST)
        assert h[Header.MESSAGE_TYPE] == "data_request"

    def test_full_headers(self) -> None:
        h = make_headers(
            message_type=MessageType.DATA_REQUEST,
            source_app="ingestion",
            sequence=42,
            request_id="abc-123",
            symbol="AAPL",
            broker="alpaca",
            tracking_id="trk-001",
        )
        assert h[Header.MESSAGE_TYPE] == "data_request"
        assert h[Header.SOURCE_APP] == "ingestion"
        assert h[Header.SEQUENCE] == "42"
        assert h[Header.REQUEST_ID] == "abc-123"
        assert h[Header.SYMBOL] == "AAPL"
        assert h[Header.BROKER] == "alpaca"
        assert h[Header.TRACKING_ID] == "trk-001"

    def test_extra_kwargs_become_headers(self) -> None:
        h = make_headers(message_type=MessageType.TRADE, custom_field="custom_value")
        assert h["custom_field"] == "custom_value"

    def test_sequence_is_string(self) -> None:
        h = make_headers(message_type=MessageType.BAR, sequence=0)
        assert isinstance(h[Header.SEQUENCE], str)
        assert h[Header.SEQUENCE] == "0"

    def test_schema_version_default(self) -> None:
        h = make_headers(message_type=MessageType.BAR)
        assert h[Header.SCHEMA_VERSION] == SCHEMA_VERSION

    def test_schema_version_override(self) -> None:
        h = make_headers(message_type=MessageType.BAR, schema_version="2.0")
        assert h[Header.SCHEMA_VERSION] == "2.0"


class TestMessageModel:
    """Tests for message_model() lookup."""

    def test_known_types_return_model_class(self) -> None:
        from tradingcz.model.events import DataRequest

        cls = message_model(MessageType.DATA_REQUEST)
        assert cls is DataRequest

    def test_unknown_type_raises(self) -> None:
        try:
            message_model("bogus_type_xyz")
            raise AssertionError("Should have raised ValueError")
        except ValueError:
            pass

    def test_str_message_type_accepted(self) -> None:
        from tradingcz.model.events import DataReady

        cls = message_model(MessageType.DATA_READY)
        assert cls is DataReady


class TestParseMessage:
    """Tests for parse_message() dispatch."""

    def test_parse_data_request(self) -> None:
        from tradingcz.model.events import DataRequest

        payload = b'{"request_id":"abc","source_app":"test","symbols":["AAPL"]}'
        result = parse_message(MessageType.DATA_REQUEST, payload)
        assert isinstance(result, DataRequest)
        assert result.request_id == "abc"

    def test_parse_unknown_type_raises(self) -> None:
        try:
            parse_message("bogus", b"{}")
            raise AssertionError("Should have raised ValueError")
        except ValueError:
            pass
