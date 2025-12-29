import json
import logging
from collections.abc import Callable
from typing import Any

from confluent_kafka import KafkaException, Producer

from tradingcz.io.writer import Writer

logger = logging.getLogger(__name__)


class KafkaWriter(Writer[Any, Any]):
    def __init__(self, producer_config: dict, topic: str) -> None:
        logger.info("Initializing Kafka producer for topic %s", topic)
        self.producer = Producer(producer_config)
        self.topic = topic

    def delivery_callback(
        self,
        err: Exception | None,
        msg: Any,
        user_callback: Callable[[Exception | None, Any], None] | None = None,
    ) -> None:
        if err is not None:
            logger.error("Message delivery failed for topic %s: %s", self.topic, err)
        if user_callback:
            user_callback(err, msg)

    def write(
        self,
        key: Any,
        value: Any,
        callback: Callable[[Exception | None, Any], None] | None = None,
    ) -> None:
        try:
            self.producer.produce(
                self.topic,
                key=json.dumps(key),
                value=json.dumps(value),
                on_delivery=lambda err, msg: self.delivery_callback(err, msg, callback),
            )
            self.producer.poll(0)  # Trigger delivery reports
        except KafkaException:
            logger.exception("Failed to produce message to topic %s", self.topic)
            raise
        except Exception:
            logger.exception("Unexpected error while producing to topic %s", self.topic)
            raise
        finally:
            self.producer.flush()

    def close(self) -> None:
        logger.info("Closing Kafka producer for topic %s", self.topic)
        remaining = self.producer.flush(timeout=10.0)
        if remaining > 0:
            logger.error("%s messages not delivered for topic %s", remaining, self.topic)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
