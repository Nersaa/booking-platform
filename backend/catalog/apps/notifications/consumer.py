"""Consumer of Booking's events (RabbitMQ topic exchange `booking.events`)."""

import logging
from typing import Any

from contracts import BOOKING_EVENTS_PATTERN, BOOKING_EXCHANGE, BookingEvent
from django.db import close_old_connections
from kombu import Connection, Exchange, Queue
from kombu.message import Message
from kombu.mixins import ConsumerMixin
from pydantic import ValidationError

from apps.notifications.services import handle_booking_event

logger = logging.getLogger(__name__)

DEAD_LETTER_QUEUE = Queue(
    "catalog.booking-events.dlq", durable=True, queue_arguments={"x-queue-type": "quorum"}
)
BOOKING_EVENTS_QUEUE = Queue(
    "catalog.booking-events",
    Exchange(BOOKING_EXCHANGE, type="topic", durable=True),
    routing_key=BOOKING_EVENTS_PATTERN,
    durable=True,
    queue_arguments={
        "x-queue-type": "quorum",
        # A message that keeps failing is parked in the DLQ instead of looping forever.
        "x-delivery-limit": 5,
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": DEAD_LETTER_QUEUE.name,
    },
)


class BookingEventConsumer(ConsumerMixin):
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def get_consumers(self, consumer: Any, channel: Any) -> list[Any]:
        DEAD_LETTER_QUEUE(channel).declare()
        return [
            consumer(
                queues=[BOOKING_EVENTS_QUEUE],
                callbacks=[self.on_message],
                accept=["json"],
                prefetch_count=10,
            )
        ]

    def on_message(self, body: Any, message: Message) -> None:
        try:
            event = BookingEvent.model_validate(body)
        except ValidationError:
            logger.exception("Malformed booking event, sending to the dead-letter queue")
            message.reject()
            return

        close_old_connections()
        try:
            handled = handle_booking_event(event)
        except Exception:
            logger.exception("Failed to handle %s %s, will retry", event.event_type, event.event_id)
            message.requeue()
            return
        message.ack()
        logger.info(
            "%s %s %s", event.event_type, event.event_id, "handled" if handled else "duplicate"
        )
