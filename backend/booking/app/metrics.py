"""Business metrics. HTTP metrics come from prometheus-fastapi-instrumentator (see main)."""

from prometheus_client import Counter

BOOKING_STATUS_CHANGES = Counter(
    "booking_status_changes_total", "Bookings entering a status.", ["status"]
)
