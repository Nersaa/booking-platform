"""Messages exchanged between services. Changes must stay backward compatible:
add optional fields only; anything else needs a new event type."""

from contracts.bookings import BookingEvent, BookingEventType, BookingSnapshot, CancelledBy
from contracts.listings import ListingEvent, ListingEventType, ListingSnapshot
from contracts.topology import (
    BOOKING_EVENTS_PATTERN,
    BOOKING_EXCHANGE,
    CATALOG_EXCHANGE,
    LISTING_EVENTS_PATTERN,
)

__all__ = [
    "BOOKING_EVENTS_PATTERN",
    "BOOKING_EXCHANGE",
    "CATALOG_EXCHANGE",
    "LISTING_EVENTS_PATTERN",
    "BookingEvent",
    "BookingEventType",
    "BookingSnapshot",
    "CancelledBy",
    "ListingEvent",
    "ListingEventType",
    "ListingSnapshot",
]
