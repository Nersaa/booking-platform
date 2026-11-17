from django.conf import settings
from django.db import models

from apps.listings.models import Listing


class Favorite(models.Model):
    """A listing the user saved to look at later."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites"
    )
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("user", "listing"), name="favorite_once_per_listing")
        ]

    def __str__(self) -> str:
        return f"{self.user_id} saved {self.listing_id}"
