from celery import shared_task

from apps.outbox.services import outbox_purge_published


@shared_task
def purge_published_events() -> int:
    return outbox_purge_published()
