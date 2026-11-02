from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bookings.models import Booking
from app.payments.models import Payment, PaymentStatus, Refund


async def schedule_refund(session: AsyncSession, booking: Booking, amount: int) -> Refund | None:
    """Record a refund of the booking's successful payment; a job sends it to the provider."""
    if amount <= 0:
        return None
    payment = await session.scalar(
        select(Payment).where(
            Payment.booking_id == booking.id, Payment.status == PaymentStatus.SUCCEEDED
        )
    )
    if payment is None:
        return None
    refund = Refund(booking_id=booking.id, payment_id=payment.id, amount=amount)
    session.add(refund)
    booking.refund_amount = amount
    return refund
