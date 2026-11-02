"""Worker process: consumes Catalog events and runs background jobs.

Started with `faststream run app.worker:app`.
"""

import logging
from typing import Any

from contracts import BOOKING_EXCHANGE
from faststream import FastStream
from faststream.rabbit import Channel, ExchangeType, RabbitBroker, RabbitExchange

from app.db import Database
from app.jobs import BackgroundJobs
from app.listings.consumer import DEAD_LETTER_QUEUE, register_listing_consumer
from app.payments.provider import HttpPaymentProvider
from app.settings import get_settings

BOOKING_EVENTS = RabbitExchange(BOOKING_EXCHANGE, type=ExchangeType.TOPIC, durable=True)


def create_worker() -> FastStream:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    db = Database(settings.database_url)
    provider = HttpPaymentProvider.build(
        settings.payment_provider_url, settings.payment_provider_api_key
    )
    # on_return_raises: an event no queue would receive fails and stays in the outbox.
    broker = RabbitBroker(settings.rabbitmq_url, default_channel=Channel(on_return_raises=True))
    register_listing_consumer(broker, db)

    async def publish(routing_key: str, body: dict[str, Any], message_id: str) -> None:
        await broker.publish(
            body,
            exchange=BOOKING_EVENTS,
            routing_key=routing_key,
            message_id=message_id,
            persist=True,
            mandatory=True,
            timeout=10,
        )

    jobs = BackgroundJobs(db, provider, publish)

    async def after_startup() -> None:
        await broker.declare_queue(DEAD_LETTER_QUEUE)
        await broker.declare_exchange(BOOKING_EVENTS)
        jobs.start()

    async def on_shutdown() -> None:
        await jobs.stop()
        await provider.close()
        await db.dispose()

    return FastStream(broker, after_startup=[after_startup], on_shutdown=[on_shutdown])


app = create_worker()
