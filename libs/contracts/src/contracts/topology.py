# Durable topic exchange that Catalog publishes domain events to.
# The routing key of every message equals its event type, e.g. "listing.published".
CATALOG_EXCHANGE = "catalog.events"
LISTING_EVENTS_PATTERN = "listing.*"
