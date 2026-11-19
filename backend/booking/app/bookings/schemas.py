from datetime import date, datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from app.bookings.models import Booking, BookingMessage, BookingStatus
from app.payments.models import Payment, PaymentStatus


class BookingIn(BaseModel):
    listing_id: UUID
    check_in: date
    check_out: date
    guests: int = Field(ge=1, le=50)


class CancelIn(BaseModel):
    reason: str = Field("", max_length=500)


class BookingOut(BaseModel):
    id: UUID
    listing_id: UUID
    guest_id: UUID
    host_id: UUID
    status: BookingStatus
    check_in: date
    check_out: date
    guests: int
    currency: str
    subtotal: int
    discount: int
    cleaning_fee: int
    total: int
    refund_amount: int
    hold_expires_at: datetime | None = Field(
        description="Pay (or, for a request, the host answers) before this moment, "
        "or the dates are released."
    )
    cancelled_by: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, booking: Booking) -> Self:
        return cls(
            id=booking.id,
            listing_id=booking.listing_id,
            guest_id=booking.guest_id,
            host_id=booking.host_id,
            status=BookingStatus(booking.status),
            check_in=booking.check_in,
            check_out=booking.check_out,
            guests=booking.guests,
            currency=booking.currency,
            subtotal=booking.subtotal,
            discount=booking.discount,
            cleaning_fee=booking.cleaning_fee,
            total=booking.total,
            refund_amount=booking.refund_amount,
            hold_expires_at=booking.hold_expires_at,
            cancelled_by=booking.cancelled_by,
            created_at=booking.created_at,
        )


class PaymentOut(BaseModel):
    id: UUID
    booking_id: UUID
    status: PaymentStatus
    amount: int
    currency: str
    checkout_url: str = Field(description="Send the guest here to pay.")

    @classmethod
    def from_model(cls, payment: Payment) -> Self:
        return cls(
            id=payment.id,
            booking_id=payment.booking_id,
            status=PaymentStatus(payment.status),
            amount=payment.amount,
            currency=payment.currency,
            checkout_url=payment.checkout_url,
        )


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class MessageOut(BaseModel):
    id: UUID
    text: str
    from_host: bool = Field(description="False when the guest wrote it.")
    created_at: datetime

    @classmethod
    def from_model(cls, message: BookingMessage, booking: Booking) -> Self:
        return cls(
            id=message.id,
            text=message.text,
            from_host=message.author_id == booking.host_id,
            created_at=message.created_at,
        )
