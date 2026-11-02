"""Imports every model so that `Base.metadata` is complete (used by Alembic)."""

from app.availability.models import AvailabilityBlock, ListingPricing, SeasonalRate
from app.bookings.models import Booking
from app.db import Base
from app.idempotency import IdempotencyKey
from app.listings.models import Listing
from app.outbox import OutboxEvent
from app.payments.models import Payment, ProcessedWebhook, Refund

__all__ = [
    "AvailabilityBlock",
    "Base",
    "Booking",
    "IdempotencyKey",
    "Listing",
    "ListingPricing",
    "OutboxEvent",
    "Payment",
    "ProcessedWebhook",
    "Refund",
    "SeasonalRate",
]
