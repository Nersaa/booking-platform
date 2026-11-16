from celery import shared_task
from contracts import CATALOG_EXCHANGE
from django.conf import settings

from apps.outbox.models import OutboxEvent
from apps.outbox.publisher import AmqpPublisher
from apps.outbox.services import outbox_purge_published, outbox_relay_batch


@shared_task
def relay_outbox() -> int:
    """Send pending events to RabbitMQ. Celery beat runs it every second."""
    if not OutboxEvent.objects.filter(published_at__isnull=True).exists():
        return 0
    with AmqpPublisher(settings.EVENT_BUS_URL, CATALOG_EXCHANGE) as publisher:
        return outbox_relay_batch(publisher=publisher)


@shared_task
def purge_published_events() -> int:
    return outbox_purge_published()
