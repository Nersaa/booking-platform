import uuid

from django.db import models
from django.db.models import Q


class OutboxEvent(models.Model):
    """A domain event saved in the same transaction as the change that caused it.

    The relay publishes pending rows to the message broker afterwards, so an event is
    never lost and never sent for a change that was rolled back.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    routing_key = models.CharField(max_length=100)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [
            # The relay only ever scans pending events; keep that index tiny.
            models.Index(
                fields=("created_at",),
                name="outbox_pending_idx",
                condition=Q(published_at__isnull=True),
            ),
            models.Index(fields=("published_at",), name="outbox_published_at_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.routing_key} {self.id}"
