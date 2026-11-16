import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.common.models import TimeStampedModel
from apps.listings.models import Listing


class ReviewableStay(models.Model):
    """A finished stay, recorded from Booking's `booking.completed` event.

    Only guests who actually stayed can review, once per booking, within a time window.
    """

    booking_id = models.UUIDField(primary_key=True)
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="+")
    guest = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    check_in = models.DateField()
    check_out = models.DateField()
    review_deadline = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=("guest", "review_deadline"))]

    def __str__(self) -> str:
        return f"Stay {self.booking_id}"


class Review(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stay = models.OneToOneField(ReviewableStay, on_delete=models.PROTECT, related_name="review")
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="reviews")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews"
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    text = models.TextField(max_length=2000)
    host_reply = models.TextField(max_length=2000, blank=True)
    host_replied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("listing", "-created_at"))]
        constraints = [
            models.CheckConstraint(
                condition=Q(rating__gte=1, rating__lte=5), name="review_rating_range"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.rating}/5 for {self.listing_id}"
