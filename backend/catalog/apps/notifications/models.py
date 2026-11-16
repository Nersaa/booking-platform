from django.db import models


class ProcessedEvent(models.Model):
    """Events already handled. Brokers deliver at least once; this makes handling once."""

    event_id = models.UUIDField(primary_key=True)
    event_type = models.CharField(max_length=100)
    processed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.event_type} {self.event_id}"
