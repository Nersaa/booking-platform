"""Messages exchanged between services. Changes must stay backward compatible:
add optional fields only; anything else needs a new event type."""

from contracts.listings import ListingEvent, ListingEventType, ListingSnapshot
from contracts.topology import CATALOG_EXCHANGE, LISTING_EVENTS_PATTERN

__all__ = [
    "CATALOG_EXCHANGE",
    "LISTING_EVENTS_PATTERN",
    "ListingEvent",
    "ListingEventType",
    "ListingSnapshot",
]
