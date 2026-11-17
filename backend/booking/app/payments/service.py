import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal
from app.bookings.models import Booking, BookingStatus
from app.bookings.service import confirm_paid_booking
from app.errors import ConflictError, NotFoundError, ServiceUnavailableError
from app.listings.models import Listing
from app.payments.models import Payment, PaymentStatus, ProcessedWebhook
from app.payments.provider import PaymentProvider, PaymentProviderError
from app.payments.refunds import refund_booking
from app.payments.webhooks import WebhookEvent, WebhookType

logger = logging.getLogger(__name__)


class BookingNotPayableError(ConflictError):
    code = "booking_not_payable"


async def start_payment(
    session: AsyncSession,
    provider: PaymentProvider,
    guest: Principal,
    booking_id: UUID,
    return_url: str | None = None,
) -> Payment:
    """Creates a payment at the provider; the guest pays on its checkout page and is sent
    back to `return_url` afterwards."""
    booking = await session.scalar(
        select(Booking)
        .where(Booking.id == booking_id, Booking.guest_id == guest.user_id)
        .with_for_update()
    )
    if booking is None:
        raise NotFoundError("Booking not found.")
    if booking.status != BookingStatus.PENDING_PAYMENT:
        raise BookingNotPayableError(f"A '{booking.status}' booking cannot be paid.")
    if booking.hold_expires_at is None or booking.hold_expires_at <= datetime.now(UTC):
        raise BookingNotPayableError("The hold has expired. Please book again.")

    # One open checkout per booking: asking again returns the same one.
    open_payment = await session.scalar(
        select(Payment).where(
            Payment.booking_id == booking.id, Payment.status == PaymentStatus.PENDING
        )
    )
    if open_payment is not None:
        return open_payment

    payment = Payment(booking_id=booking.id, amount=booking.total, currency=booking.currency)
    session.add(payment)
    await session.flush()
    try:
        created = await provider.create_payment(
            amount=payment.amount,
            currency=payment.currency,
            reference=str(payment.id),
            idempotency_key=str(payment.id),
            description=await _description(session, booking),
            return_url=return_url,
        )
    except PaymentProviderError as exc:
        raise ServiceUnavailableError("The payment provider is unavailable. Try again.") from exc
    payment.provider_payment_id = created.id
    payment.checkout_url = created.checkout_url
    return payment


async def _description(session: AsyncSession, booking: Booking) -> str:
    """What the guest sees on the checkout page, e.g. "Sunny loft, 3 nights from 7 Jun"."""
    title = await session.scalar(select(Listing.title).where(Listing.id == booking.listing_id))
    nights = (booking.check_out - booking.check_in).days
    when = booking.check_in.strftime("%d %b").lstrip("0")
    return f"{title}, {nights} night{'s' if nights != 1 else ''} from {when}"[:200]


async def handle_webhook(
    session: AsyncSession, provider: PaymentProvider, event: WebhookEvent
) -> None:
    first_delivery = await session.scalar(
        insert(ProcessedWebhook)
        .values(event_id=event.id, event_type=event.type)
        .on_conflict_do_nothing()
        .returning(ProcessedWebhook.event_id)
    )
    if first_delivery is None:
        logger.info("Webhook %s already processed", event.id)
        return
    if event.type not in (WebhookType.PAYMENT_SUCCEEDED, WebhookType.PAYMENT_FAILED):
        return  # refund notifications need no action: the refund was recorded when sent

    payment = await session.scalar(
        select(Payment).where(Payment.id == event.data.reference).with_for_update()
    )
    if payment is None:
        logger.warning("Webhook %s refers to unknown payment %s", event.id, event.data.reference)
        return
    if payment.status != PaymentStatus.PENDING:
        return

    if event.type is WebhookType.PAYMENT_FAILED:
        payment.status = PaymentStatus.FAILED
        return

    payment.status = PaymentStatus.SUCCEEDED
    booking = await session.get_one(Booking, payment.booking_id, with_for_update=True)
    if not await confirm_paid_booking(session, booking):
        # Paid after the hold expired or the guest cancelled: return the money.
        logger.warning("Late payment %s for %s booking, refunding", payment.id, booking.status)
        await refund_booking(session, provider, booking, payment.amount)
