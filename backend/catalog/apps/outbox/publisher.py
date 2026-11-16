"""Publishing events to a RabbitMQ topic exchange."""

from types import TracebackType
from typing import Any, Protocol, Self

from amqp.exceptions import AMQPError
from kombu import Connection, Exchange
from kombu.exceptions import KombuError


class PublishError(Exception):
    pass


class Publisher(Protocol):
    def publish(self, *, routing_key: str, body: dict[str, Any], message_id: str) -> None: ...


class AmqpPublisher:
    """Sends persistent JSON messages over one connection; use it as a context manager."""

    def __init__(self, url: str, exchange: str) -> None:
        self._connection = Connection(url)
        self._exchange = Exchange(exchange, type="topic", durable=True)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._connection.release()

    def publish(self, *, routing_key: str, body: dict[str, Any], message_id: str) -> None:
        try:
            self._connection.Producer().publish(
                body,
                exchange=self._exchange,
                declare=[self._exchange],
                routing_key=routing_key,
                serializer="json",
                delivery_mode=2,  # persistent: survives a broker restart
                message_id=message_id,
            )
        except (OSError, AMQPError, KombuError) as exc:
            raise PublishError(f"Could not publish {message_id}: {exc}") from exc
