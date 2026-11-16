"""Consumes Catalog listing events into the local read model."""

import logging

from contracts import CATALOG_EXCHANGE, LISTING_EVENTS_PATTERN, ListingEvent
from faststream import AckPolicy
from faststream.rabbit import ExchangeType, QueueType, RabbitBroker, RabbitExchange, RabbitQueue

from app.db import Database
from app.listings.sync import apply_listing_snapshot

logger = logging.getLogger(__name__)

CATALOG_EVENTS = RabbitExchange(CATALOG_EXCHANGE, type=ExchangeType.TOPIC, durable=True)
DEAD_LETTER_QUEUE = RabbitQueue(
    "booking.listing-events.dlq", queue_type=QueueType.QUORUM, durable=True
)
LISTING_EVENTS_QUEUE = RabbitQueue(
    "booking.listing-events",
    queue_type=QueueType.QUORUM,
    durable=True,
    routing_key=LISTING_EVENTS_PATTERN,
    arguments={
        # A message that keeps failing (bad payload, bug) is parked instead of looping forever.
        "x-delivery-limit": 5,
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": DEAD_LETTER_QUEUE.name,
    },
)


def register_listing_consumer(broker: RabbitBroker, db: Database) -> None:
    # NACK_ON_ERROR requeues on failure, so a database outage only delays processing.
    @broker.subscriber(LISTING_EVENTS_QUEUE, CATALOG_EVENTS, ack_policy=AckPolicy.NACK_ON_ERROR)
    async def on_listing_event(event: ListingEvent) -> None:
        async with db.sessions.begin() as session:
            applied = await apply_listing_snapshot(session, event.listing)
        logger.info(
            "%s %s v%d: %s",
            event.event_type,
            event.listing.id,
            event.listing.version,
            "applied" if applied else "skipped as stale",
        )
