import logging
import signal
import threading
from argparse import ArgumentParser
from typing import Any

from contracts import CATALOG_EXCHANGE
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.outbox.publisher import AmqpPublisher
from apps.outbox.services import outbox_relay_forever

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Publish outbox events to the message broker until stopped."
    requires_system_checks: list[str] = []

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--poll-interval", type=float, default=0.5, help="Seconds when idle.")
        parser.add_argument("--max-backoff", type=float, default=30.0, help="Seconds.")

    def handle(self, *args: Any, **options: Any) -> None:
        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())

        publisher = AmqpPublisher(settings.EVENT_BUS_URL, CATALOG_EXCHANGE)
        logger.info("Outbox relay started")
        try:
            outbox_relay_forever(
                publisher=publisher,
                stop=stop,
                batch_size=options["batch_size"],
                poll_interval=options["poll_interval"],
                max_backoff=options["max_backoff"],
            )
        finally:
            publisher.close()
            logger.info("Outbox relay stopped")
