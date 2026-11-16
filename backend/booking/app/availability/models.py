"""Prices and availability, owned by Booking.

Money is stored as integer minor units (cents) to avoid rounding errors.
Date periods are half-open ranges [start, end): `end` is the check-out day, so the
period covers the nights from `start` up to, but not including, `end`.
"""

import uuid
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import DATERANGE, ExcludeConstraint, Range
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def period_bounds(period: Range[date]) -> tuple[date, date]:
    """Stored periods are always bounded and non-empty (enforced by the API and constraints)."""
    if period.lower is None or period.upper is None:
        raise ValueError(f"Unexpected unbounded period: {period}")
    return period.lower, period.upper


class ListingPricing(Base):
    __tablename__ = "listing_pricing"

    listing_id: Mapped[UUID] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True
    )
    currency: Mapped[str] = mapped_column(String(3))
    nightly_price: Mapped[int]
    weekend_price: Mapped[int | None] = mapped_column(comment="Friday and Saturday nights")
    cleaning_fee: Mapped[int] = mapped_column(default=0)
    min_nights: Mapped[int] = mapped_column(SmallInteger, default=1)
    max_nights: Mapped[int] = mapped_column(SmallInteger, default=365)
    weekly_discount_percent: Mapped[int] = mapped_column(SmallInteger, default=0)
    monthly_discount_percent: Mapped[int] = mapped_column(SmallInteger, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("nightly_price > 0", name="nightly_price_positive"),
        CheckConstraint(
            "weekend_price IS NULL OR weekend_price > 0", name="weekend_price_positive"
        ),
        CheckConstraint("cleaning_fee >= 0", name="cleaning_fee_non_negative"),
        CheckConstraint("min_nights >= 1 AND max_nights >= min_nights", name="nights_range"),
        CheckConstraint("weekly_discount_percent BETWEEN 0 AND 90", name="weekly_discount"),
        CheckConstraint("monthly_discount_percent BETWEEN 0 AND 90", name="monthly_discount"),
    )


class SeasonalRate(Base):
    """A nightly price that overrides the regular one for a period, e.g. the summer season."""

    __tablename__ = "seasonal_rates"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[UUID] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"))
    period: Mapped[Range[date]] = mapped_column(DATERANGE)
    nightly_price: Mapped[int]

    __table_args__ = (
        # The database itself guarantees that seasons of one listing never overlap.
        ExcludeConstraint(
            ("listing_id", "="), ("period", "&&"), using="gist", name="seasonal_rates_no_overlap"
        ),
        CheckConstraint("NOT isempty(period)", name="period_not_empty"),
        CheckConstraint("nightly_price > 0", name="nightly_price_positive"),
    )


class AvailabilityBlock(Base):
    """Dates the host closed for guests (personal use, renovation and so on)."""

    __tablename__ = "availability_blocks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[UUID] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"))
    period: Mapped[Range[date]] = mapped_column(DATERANGE)
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        ExcludeConstraint(
            ("listing_id", "="),
            ("period", "&&"),
            using="gist",
            name="availability_blocks_no_overlap",
        ),
        CheckConstraint("NOT isempty(period)", name="period_not_empty"),
    )
