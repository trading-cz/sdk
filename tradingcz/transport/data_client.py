"""Data request/response client — thin helper that binds the generic
``RequestReplyClient`` to the ``DataRequest → DataReady|DataError`` protocol.

Shared by all strategy apps that need to request data from ingestion.
"""

from tradingcz.model.events import DataError, DataReady, DataRequest, parse_event
from tradingcz.serialization import JsonCodec
from tradingcz.serialization.protocol import Deserializer
from tradingcz.transport.protocol import Channel
from tradingcz.transport.request_reply import RequestReplyClient


class _DataResponseDeserializer(Deserializer[DataReady | DataError]):
    """Deserialize only DataReady/DataError, skipping other event types."""

    def deserialize(self, payload: bytes) -> DataReady | DataError:
        """Parse *payload*; raises ValueError if not a data response."""
        event = parse_event(payload)
        if isinstance(event, (DataReady, DataError)):
            return event
        raise ValueError(f"Not a data response: {type(event).__name__}")

    def content_type(self) -> str:
        """Return the MIME type (JSON)."""
        return "application/json"


_Response = DataReady | DataError


def create_data_client(
    channel: Channel,
    *,
    timeout: float = 30.0,
) -> RequestReplyClient[DataRequest, _Response]:
    """Create a :class:`RequestReplyClient` configured for data requests.

    Args:
        channel: Events channel (``dev-event``) — requests and responses
                 flow on the same topic.
        timeout: Per-request timeout in seconds.

    Returns:
        A ready-to-``start()`` client instance.

    Usage::

        async with create_data_client(events_channel, timeout=30) as client:
            response = await client.request(data_request)
            data_channel = await transport.channel(response.data_topic)
    """
    return RequestReplyClient[DataRequest, _Response](
        channel=channel,
        request_serializer=JsonCodec(DataRequest),
        response_deserializer=_DataResponseDeserializer(),
        request_id_of=lambda r: r.request_id,
        response_id_of=lambda r: r.request_id,
        timeout=timeout,
    )
