"""Refunds are sent to the provider right away.

If the provider is down, the whole operation (cancellation or webhook) fails with 503 and
nothing is saved, so it can simply be retried. The booking id is the idempotency key, so
a retry never refunds twice.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bookings.models import Booking
from app.errors import ServiceUnavailableError
from app.payments.models import Payment, PaymentStatus
from app.payments.provider import PaymentProvider, PaymentProviderError


async def refund_booking(
    session: AsyncSession, provider: PaymentProvider, booking: Booking, amount: int
) -> None:
    if amount <= 0:
        return
    payment = await session.scalar(
        select(Payment).where(
            Payment.booking_id == booking.id, Payment.status == PaymentStatus.SUCCEEDED
        )
    )
    if payment is None or payment.provider_payment_id is None:
        return
    try:
        await provider.create_refund(
            payment_id=payment.provider_payment_id,
            amount=amount,
            reference=str(booking.id),
            idempotency_key=f"refund-{booking.id}",
        )
    except PaymentProviderError as exc:
        raise ServiceUnavailableError("The payment provider is unavailable. Try again.") from exc
    booking.refund_amount = amount
