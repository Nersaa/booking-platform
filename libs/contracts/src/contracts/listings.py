"""Listing events published by Catalog.

Every event carries a full snapshot of the listing (event-carried state transfer), so a
consumer never has to call Catalog back. `version` grows with every change: consumers
apply a snapshot only if it is newer than what they have, which makes redelivered and
reordered messages harmless.
"""

from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ListingEventType(StrEnum):
    PUBLISHED = "listing.published"
    UPDATED = "listing.updated"
    ARCHIVED = "listing.archived"


class ListingSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    version: int = Field(ge=1)
    host_id: UUID
    is_listed: bool = Field(description="False once the listing is archived.")
    title: str = Field(max_length=120)
    property_type: str = Field(max_length=20)
    country: str = Field(min_length=2, max_length=2)
    city: str = Field(max_length=100)
    latitude: Decimal = Field(ge=-90, le=90, max_digits=9, decimal_places=6)
    longitude: Decimal = Field(ge=-180, le=180, max_digits=9, decimal_places=6)
    max_guests: int = Field(ge=1)
    bedrooms: int = Field(ge=0)
    beds: int = Field(ge=1)
    bathrooms: int = Field(ge=0)
    amenities: tuple[str, ...]
    cover_photo_url: str | None
    # Added in stage 4; the defaults keep older events readable.
    rating: Decimal | None = Field(
        None, ge=1, le=5, max_digits=3, decimal_places=2, description="Average review score."
    )
    review_count: int = Field(0, ge=0)


class ListingEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: UUID
    event_type: ListingEventType
    occurred_at: AwareDatetime
    listing: ListingSnapshot

    @property
    def routing_key(self) -> str:
        return self.event_type.value
