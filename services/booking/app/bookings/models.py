import uuid
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ColumnElement,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    and_,
    func,
    or_,
    text,
)
from sqlalchemy.dialects.postgresql import DATERANGE, ExcludeConstraint, Range
from sqlalchemy.orm import Mapped, mapped_column

from app.availability.models import period_bounds
from app.db import Base


class BookingStatus(StrEnum):
    PENDING_PAYMENT = "pending_payment"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    COMPLETED = "completed"


# Bookings in these states hold their dates.
ACTIVE_STATUSES = (BookingStatus.PENDING_PAYMENT, BookingStatus.CONFIRMED)


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[UUID] = mapped_column(ForeignKey("listings.id"))
    guest_id: Mapped[UUID]
    host_id: Mapped[UUID] = mapped_column(index=True)
    period: Mapped[Range[date]] = mapped_column(DATERANGE)
    guests: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String(20), default=BookingStatus.PENDING_PAYMENT)

    # Price as quoted when the booking was made; later price changes do not affect it.
    currency: Mapped[str] = mapped_column(String(3))
    subtotal: Mapped[int]
    discount: Mapped[int]
    cleaning_fee: Mapped[int]
    total: Mapped[int]

    refund_amount: Mapped[int] = mapped_column(default=0)

    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by: Mapped[str | None] = mapped_column(String(10))
    cancellation_reason: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # The core guarantee of the platform: two active bookings of one listing can never
        # share a night, whatever the application code does and however requests race.
        ExcludeConstraint(
            ("listing_id", "="),
            ("period", "&&"),
            using="gist",
            where=text("status IN ('pending_payment', 'confirmed')"),
            name="bookings_no_overlap",
        ),
        CheckConstraint(
            "status IN ('pending_payment', 'confirmed', 'cancelled', 'expired', 'completed')",
            name="status_valid",
        ),
        CheckConstraint("NOT isempty(period)", name="period_not_empty"),
        CheckConstraint("guests >= 1", name="guests_positive"),
        CheckConstraint("total >= 0 AND total = subtotal - discount + cleaning_fee", name="total"),
        CheckConstraint("refund_amount BETWEEN 0 AND total", name="refund_amount"),
        Index(
            "ix_bookings_pending_holds",
            "hold_expires_at",
            postgresql_where=text("status = 'pending_payment'"),
        ),
        # Serves the guest's keyset-paginated list: newest first.
        Index("ix_bookings_guest_id_created_at", "guest_id", "created_at", "id"),
    )

    @classmethod
    def holds_dates(cls) -> ColumnElement[bool]:
        """Confirmed, or awaiting payment within its hold. A stale hold blocks nothing,
        even before the sweeper expires it."""
        return or_(
            cls.status == BookingStatus.CONFIRMED,
            and_(
                cls.status == BookingStatus.PENDING_PAYMENT,
                cls.hold_expires_at > func.now(),
            ),
        )

    @property
    def check_in(self) -> date:
        return period_bounds(self.period)[0]

    @property
    def check_out(self) -> date:
        return period_bounds(self.period)[1]
