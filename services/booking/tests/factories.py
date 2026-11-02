from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from contracts import ListingEvent, ListingEventType, ListingSnapshot


def snapshot(**fields: Any) -> ListingSnapshot:
    data: dict[str, Any] = {
        "id": uuid4(),
        "version": 2,
        "host_id": uuid4(),
        "is_listed": True,
        "title": "Sunny apartment",
        "property_type": "apartment",
        "country": "PT",
        "city": "Lisbon",
        "latitude": Decimal("38.710000"),
        "longitude": Decimal("-9.137000"),
        "max_guests": 4,
        "bedrooms": 2,
        "beds": 2,
        "bathrooms": 1,
        "amenities": ("wifi", "kitchen"),
        "cover_photo_url": "http://testserver/media/public/listings/1/1/thumb.webp",
    }
    data.update(fields)
    return ListingSnapshot(**data)


def listing_event(
    listing: ListingSnapshot, event_type: ListingEventType = ListingEventType.PUBLISHED
) -> ListingEvent:
    return ListingEvent(
        event_id=uuid4(), event_type=event_type, occurred_at=datetime.now(UTC), listing=listing
    )
