"""Publishing to RabbitMQ with publisher confirms."""

import logging
from typing import Any, Protocol

from amqp.exceptions import AMQPError
from kombu import Connection, Exchange, Producer
from kombu.exceptions import KombuError
from kombu.message import Message

logger = logging.getLogger(__name__)


class PublishError(Exception):
    pass


class Publisher(Protocol):
    def publish(self, *, routing_key: str, body: dict[str, Any], message_id: str) -> None:
        """Return only once the broker has stored the message; raise PublishError otherwise."""


class AmqpPublisher:
    """Publishes persistent messages to a topic exchange and waits for broker confirms.

    Messages are `mandatory`: if no queue is bound for the routing key yet (e.g. the
    consumer has never started), the broker returns the message and the publish fails,
    so the event stays in the outbox instead of being silently dropped.
    """

    def __init__(self, url: str, exchange: str, *, timeout: float = 10.0) -> None:
        self._connection = Connection(url, transport_options={"confirm_publish": True})
        self._exchange = Exchange(exchange, type="topic", durable=True)
        self._timeout = timeout
        self._producer: Producer | None = None
        self._returned: list[str] = []

    def publish(self, *, routing_key: str, body: dict[str, Any], message_id: str) -> None:
        self._returned.clear()
        try:
            self._get_producer().publish(
                body,
                routing_key=routing_key,
                serializer="json",
                delivery_mode=2,  # persistent
                mandatory=True,
                message_id=message_id,
                timeout=self._timeout,
            )
        except (OSError, AMQPError, KombuError) as exc:
            self.close()
            raise PublishError(f"Could not publish {message_id}: {exc}") from exc
        if self._returned:
            raise PublishError(f"Broker returned {message_id}: {self._returned[0]}")

    def close(self) -> None:
        self._producer = None
        self._connection.release()

    def _get_producer(self) -> Producer:
        if self._producer is None:
            channel = self._connection.channel()
            self._exchange(channel).declare()
            self._producer = Producer(channel, exchange=self._exchange, on_return=self._on_return)
        return self._producer

    def _on_return(
        self, exc: Exception, exchange: Exchange | str, routing_key: str, message: Message
    ) -> None:
        self._returned.append(f"{exc} (routing key {routing_key!r})")
