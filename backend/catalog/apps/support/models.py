import uuid

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class TicketTopic(models.TextChoices):
    BOOKING = "booking", "A booking"
    PAYMENT = "payment", "Payment or refund"
    LISTING = "listing", "My listing (for hosts)"
    ACCOUNT = "account", "My account"
    OTHER = "other", "Something else"


class TicketStatus(models.TextChoices):
    OPEN = "open", "Waiting for support"
    ANSWERED = "answered", "Answered"
    CLOSED = "closed", "Closed"


class Ticket(TimeStampedModel):
    """A support request: a subject and a conversation between the user and support."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="support_tickets"
    )
    topic = models.CharField(max_length=20, choices=TicketTopic.choices)
    subject = models.CharField(max_length=150)
    # Booking lives in another service, so only its id is kept here.
    booking_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=TicketStatus.choices, default=TicketStatus.OPEN
    )

    class Meta:
        ordering = ("-updated_at",)
        indexes = [models.Index(fields=("status", "-updated_at"))]
        verbose_name = "support request"

    def __str__(self) -> str:
        return self.subject


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    from_support = models.BooleanField(default=False)
    text = models.TextField(max_length=5000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)

    def __str__(self) -> str:
        return f"{'Support' if self.from_support else 'User'}: {self.text[:50]}"
