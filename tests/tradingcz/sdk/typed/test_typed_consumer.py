"""Unit tests for TypedConsumer."""
# pylint: disable=protected-access

from pydantic import BaseModel

from tradingcz.sdk.models.enums.event import Broker, EventType
from tradingcz.sdk.models.events import DataReady
from tradingcz.sdk.transport.kafka_header import Header
from tradingcz.sdk.transport.kafka_message import KafkaMessage
from tradingcz.sdk.transport.kafka_settings import KafkaSettings
from tradingcz.sdk.typed.typed_consumer import TypedConsumer


def test_types_registered_after_construction_are_dispatched() -> None:
    types: dict[str, type[BaseModel]] = {}  # RequestReply may start its listener before any type is registered
    consumer = TypedConsumer("topic", KafkaSettings(consumer_group="g"), types, group_suffix="s")
    types[EventType.DATA_READY] = DataReady

    ready = DataReady(broker=Broker.ALPACA, data_topic="d")
    msg = KafkaMessage(payload=ready.model_dump_json().encode(), headers={Header.EVENT_TYPE: EventType.DATA_READY})
    assert consumer._dispatch(msg) == (EventType.DATA_READY, ready)
