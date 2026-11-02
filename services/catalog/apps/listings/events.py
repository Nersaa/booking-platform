"""Listing events for other services, recorded in the outbox inside the listing's transaction."""

import uuid

from contracts import ListingEvent, ListingEventType, ListingSnapshot
from django.utils import timezone

from apps.common import storage
from apps.listings.models import Listing, ListingStatus, PhotoStatus
from apps.outbox.services import outbox_add


def listing_snapshot(listing: Listing) -> ListingSnapshot:
    cover = (
        listing.photos.filter(status=PhotoStatus.READY).order_by("position", "created_at").first()
    )
    return ListingSnapshot(
        id=listing.id,
        version=listing.version,
        host_id=listing.host_id,
        is_listed=listing.status == ListingStatus.PUBLISHED,
        title=listing.title,
        property_type=listing.property_type,
        country=listing.country,
        city=listing.city,
        latitude=listing.latitude,
        longitude=listing.longitude,
        max_guests=listing.max_guests,
        bedrooms=listing.bedrooms,
        beds=listing.beds,
        bathrooms=listing.bathrooms,
        amenities=tuple(listing.amenities.order_by("code").values_list("code", flat=True)),
        cover_photo_url=storage.public_url(cover.thumb_key) if cover else None,
    )


def emit_listing_event(listing: Listing, event_type: ListingEventType) -> None:
    event = ListingEvent(
        event_id=uuid.uuid4(),
        event_type=event_type,
        occurred_at=timezone.now(),
        listing=listing_snapshot(listing),
    )
    outbox_add(
        event_id=event.event_id,
        routing_key=event.routing_key,
        payload=event.model_dump(mode="json"),
    )
