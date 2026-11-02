"""Imports every model so that `Base.metadata` is complete (used by Alembic)."""

from app.availability.models import AvailabilityBlock, ListingPricing, SeasonalRate
from app.db import Base
from app.listings.models import Listing

__all__ = ["AvailabilityBlock", "Base", "Listing", "ListingPricing", "SeasonalRate"]
