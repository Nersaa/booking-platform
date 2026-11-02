"""Message consumer process: `faststream run app.worker:app`."""

import logging

from faststream import FastStream
from faststream.rabbit import RabbitBroker

from app.db import Database
from app.listings.consumer import DEAD_LETTER_QUEUE, register_listing_consumer
from app.settings import get_settings


def create_worker() -> FastStream:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    db = Database(settings.database_url)
    broker = RabbitBroker(settings.rabbitmq_url)
    register_listing_consumer(broker, db)

    async def declare_dead_letter_queue() -> None:
        await broker.declare_queue(DEAD_LETTER_QUEUE)

    return FastStream(
        broker, after_startup=[declare_dead_letter_queue], after_shutdown=[db.dispose]
    )


app = create_worker()
