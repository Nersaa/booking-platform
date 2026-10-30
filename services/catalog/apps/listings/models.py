import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.common.models import TimeStampedModel


class Amenity(models.Model):
    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ("name",)
        verbose_name_plural = "amenities"

    def __str__(self) -> str:
        return self.name


class PropertyType(models.TextChoices):
    APARTMENT = "apartment"
    HOUSE = "house"
    ROOM = "room"
    COTTAGE = "cottage"


class ListingStatus(models.TextChoices):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class Listing(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="listings"
    )
    title = models.CharField(max_length=120)
    description = models.TextField(max_length=5000)
    property_type = models.CharField(max_length=20, choices=PropertyType.choices)
    status = models.CharField(
        max_length=20, choices=ListingStatus.choices, default=ListingStatus.DRAFT
    )
    rejection_reason = models.TextField(blank=True)

    country = models.CharField(max_length=2, help_text="ISO 3166-1 alpha-2 code")
    city = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(Decimal(-90)), MaxValueValidator(Decimal(90))],
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(Decimal(-180)), MaxValueValidator(Decimal(180))],
    )

    max_guests = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(50)]
    )
    bedrooms = models.PositiveSmallIntegerField(default=0)
    beds = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    bathrooms = models.PositiveSmallIntegerField(default=1)
    amenities = models.ManyToManyField(Amenity, blank=True, related_name="listings")

    published_at = models.DateTimeField(null=True, blank=True)
    # Incremented on every change; consumers use it to drop stale updates.
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("host", "status")),
            models.Index(fields=("status", "-created_at")),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(latitude__gte=-90, latitude__lte=90), name="listing_latitude_range"
            ),
            models.CheckConstraint(
                condition=Q(longitude__gte=-180, longitude__lte=180),
                name="listing_longitude_range",
            ),
            models.CheckConstraint(condition=Q(max_guests__gte=1), name="listing_max_guests_gte_1"),
        ]

    def __str__(self) -> str:
        return self.title


class PhotoStatus(models.TextChoices):
    PENDING_UPLOAD = "pending_upload"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ListingPhoto(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="photos")
    status = models.CharField(
        max_length=20, choices=PhotoStatus.choices, default=PhotoStatus.PENDING_UPLOAD
    )
    content_type = models.CharField(max_length=50)
    position = models.PositiveSmallIntegerField(default=0)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("position", "created_at")
        indexes = [models.Index(fields=("status", "created_at"))]

    def __str__(self) -> str:
        return f"Photo {self.id} of {self.listing_id}"

    # Originals live under a private prefix; only processed variants are public.
    @property
    def original_key(self) -> str:
        return f"uploads/listings/{self.listing_id}/{self.id}"

    @property
    def large_key(self) -> str:
        return f"public/listings/{self.listing_id}/{self.id}/large.webp"

    @property
    def thumb_key(self) -> str:
        return f"public/listings/{self.listing_id}/{self.id}/thumb.webp"

    @property
    def storage_keys(self) -> list[str]:
        return [self.original_key, self.large_key, self.thumb_key]
