from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from kombu import Connection

from apps.common import metrics
from apps.notifications.consumer import BookingEventConsumer


class Command(BaseCommand):
    help = "Consume events from other services (booking notifications) until stopped."
    requires_system_checks: list[str] = []

    def handle(self, *args: Any, **options: Any) -> None:
        metrics.serve(settings.METRICS_PORT)
        with Connection(settings.EVENT_BUS_URL) as connection:
            BookingEventConsumer(connection).run()
