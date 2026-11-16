# Durable topic exchanges, one per publishing service.
# The routing key of every message equals its event type, e.g. "listing.published".
CATALOG_EXCHANGE = "catalog.events"
LISTING_EVENTS_PATTERN = "listing.*"

BOOKING_EXCHANGE = "booking.events"
BOOKING_EVENTS_PATTERN = "booking.*"
