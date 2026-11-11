"""Worker process: consumes Catalog events and runs background jobs.

Started with `faststream run app.worker:app`.
"""

import logging
from typing import Any

from contracts import BOOKING_EXCHANGE
from faststream import FastStream
from faststream.rabbit import Channel, ExchangeType, RabbitBroker, RabbitExchange
from prometheus_client import start_http_server

from app.db import Database
from app.jobs import BackgroundJobs
from app.listings.consumer import DEAD_LETTER_QUEUE, register_listing_consumer
from app.logs import configure_logging
from app.metrics import registry
from app.payments.provider import HttpPaymentProvider
from app.settings import get_settings

BOOKING_EVENTS = RabbitExchange(BOOKING_EXCHANGE, type=ExchangeType.TOPIC, durable=True)


def create_worker() -> FastStream:
    settings = get_settings()
    configure_logging(settings.log_level)
    db = Database(settings.database_url)
    provider = HttpPaymentProvider.build(
        settings.payment_provider_url, settings.payment_provider_api_key
    )
    # on_return_raises: an event no queue would receive fails and stays in the outbox.
    # Our logger instead of FastStream's own handlers keeps the JSON format.
    broker = RabbitBroker(
        settings.rabbitmq_url,
        default_channel=Channel(on_return_raises=True),
        logger=logging.getLogger("app.broker"),
    )
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
        start_http_server(settings.metrics_port, registry=registry())

    async def on_shutdown() -> None:
        await jobs.stop()
        await provider.close()
        await db.dispose()

    return FastStream(
        broker,
        after_startup=[after_startup],
        on_shutdown=[on_shutdown],
        logger=logging.getLogger("app.worker"),
    )


app = create_worker()
