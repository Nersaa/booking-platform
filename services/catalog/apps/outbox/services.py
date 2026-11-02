import logging
import threading
from datetime import timedelta
from typing import Any
from uuid import UUID

from django.db import DatabaseError, close_old_connections, connection, transaction
from django.utils import timezone

from apps.outbox.models import OutboxEvent
from apps.outbox.publisher import Publisher, PublishError

logger = logging.getLogger(__name__)

PUBLISHED_RETENTION = timedelta(days=7)


def outbox_add(*, event_id: UUID, routing_key: str, payload: dict[str, Any]) -> OutboxEvent:
    """Record an event as part of the caller's transaction."""
    if not connection.in_atomic_block:
        raise RuntimeError("Outbox events must be written inside the transaction they describe.")
    return OutboxEvent.objects.create(id=event_id, routing_key=routing_key, payload=payload)


def outbox_relay_batch(*, publisher: Publisher, batch_size: int = 100) -> int:
    """Publish pending events in order. Returns how many were published.

    Rows are locked with SKIP LOCKED, so several relays can run side by side. Delivery is
    at least once: if the process dies after publishing but before commit, the event is
    sent again, and consumers ignore it by version.
    """
    published: list[UUID] = []
    with transaction.atomic():
        pending = list(
            OutboxEvent.objects.select_for_update(skip_locked=True)
            .filter(published_at__isnull=True)
            .order_by("created_at")[:batch_size]
        )
        for event in pending:
            try:
                publisher.publish(
                    routing_key=event.routing_key, body=event.payload, message_id=str(event.id)
                )
            except PublishError:
                if not published:
                    raise
                break  # keep what already went out; the rest goes with the next batch
            published.append(event.id)
        OutboxEvent.objects.filter(id__in=published).update(published_at=timezone.now())
    return len(published)


def outbox_relay_forever(
    *,
    publisher: Publisher,
    stop: threading.Event,
    batch_size: int = 100,
    poll_interval: float = 0.5,
    max_backoff: float = 30.0,
) -> None:
    """Relay until `stop` is set: drain pending events, poll when idle, back off on errors."""
    backoff = poll_interval
    while not stop.is_set():
        close_old_connections()
        try:
            sent = outbox_relay_batch(publisher=publisher, batch_size=batch_size)
        except (PublishError, DatabaseError) as exc:
            logger.warning("Relay failed, retrying in %.1fs: %s", backoff, exc)
            stop.wait(backoff)
            backoff = min(backoff * 2, max_backoff)
            continue

        backoff = poll_interval
        if sent:
            logger.info("Published %d event(s)", sent)
        if sent < batch_size:
            stop.wait(poll_interval)


def outbox_purge_published(*, older_than: timedelta = PUBLISHED_RETENTION) -> int:
    deleted, _ = OutboxEvent.objects.filter(published_at__lt=timezone.now() - older_than).delete()
    return deleted
