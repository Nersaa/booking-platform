"""Booking events published by Booking.

Catalog consumes them to notify people (it owns their contact details) and, later, to
know which stays can be reviewed. Snapshots carry ids only, no personal data.
"""

from datetime import date
from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class BookingEventType(StrEnum):
    # A guest asked to book a place that needs the host's answer.
    REQUESTED = "booking.requested"
    ACCEPTED = "booking.accepted"
    DECLINED = "booking.declined"
    REQUEST_EXPIRED = "booking.request_expired"
    CONFIRMED = "booking.confirmed"
    CANCELLED = "booking.cancelled"
    COMPLETED = "booking.completed"


class CancelledBy(StrEnum):
    GUEST = "guest"
    HOST = "host"


class BookingSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    listing_id: UUID
    guest_id: UUID
    host_id: UUID
    check_in: date
    check_out: date
    guests: int = Field(ge=1)
    currency: str = Field(min_length=3, max_length=3)
    total: int = Field(ge=0, description="Minor units.")
    refund: int = Field(0, ge=0, description="Minor units refunded on cancellation.")
    cancelled_by: CancelledBy | None = None


class BookingEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: UUID
    event_type: BookingEventType
    occurred_at: AwareDatetime
    booking: BookingSnapshot

    @property
    def routing_key(self) -> str:
        return self.event_type.value
