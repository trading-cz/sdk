import json
import logging
from collections.abc import Callable
from typing import Any

from confluent_kafka import Consumer, KafkaError

from tradingcz.io.reader import Reader
from tradingcz.model.kafka_key import KafkaKey

logger = logging.getLogger(__name__)


class KafkaReader(Reader[KafkaKey, Any]):
    def __init__(self, consumer_config: dict, topic: str, poll_milli: float) -> None:
        logger.info("Initializing Kafka consumer for topic %s", topic)
        self.consumer = Consumer(consumer_config)
        self.topic = topic
        self.poll_milli = poll_milli
        self.consumer.subscribe([topic])  # Removed on_assign callback

    def read(self, callback: Callable[[KafkaKey, Any], None]) -> None:
        logger.info("Starting to read from topic %s", self.topic)
        try:
            # Initial poll to trigger group coordinator
            self.consumer.poll(0)
            logger.debug("Consumer group join triggered for %s", self.topic)

            while True:
                msg = self.consumer.poll(self.poll_milli)
                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    logger.error("Consumer error on %s: %s", self.topic, msg.error())
                    break

                try:
                    if msg.key() is None:
                        continue

                    key = KafkaKey.from_json(msg.key())
                    value = json.loads(msg.value())
                    callback(key, value)
                except Exception as exc:  # noqa: BLE001 - callbacks may raise
                    logger.exception("Error processing message on %s: %s", self.topic, exc)
                    continue

        finally:
            logger.info("Closing Kafka consumer for topic %s", self.topic)
            self.consumer.close()
