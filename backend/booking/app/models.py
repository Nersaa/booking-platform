"""Imports every model so that `Base.metadata` is complete (used by Alembic)."""

from app.availability.models import AvailabilityBlock, ListingPricing, SeasonalRate
from app.bookings.models import Booking
from app.db import Base
from app.listings.models import Listing
from app.outbox import OutboxEvent
from app.payments.models import Payment, ProcessedWebhook

__all__ = [
    "AvailabilityBlock",
    "Base",
    "Booking",
    "Listing",
    "ListingPricing",
    "OutboxEvent",
    "Payment",
    "ProcessedWebhook",
    "SeasonalRate",
]
