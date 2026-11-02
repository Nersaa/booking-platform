import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import Principal
from app.bookings.models import Booking, BookingStatus
from app.bookings.service import confirm_paid_booking
from app.errors import ConflictError, NotFoundError, ServiceUnavailableError
from app.payments.models import Payment, PaymentStatus, ProcessedWebhook, Refund, RefundStatus
from app.payments.provider import PaymentProvider, PaymentProviderError
from app.payments.refunds import schedule_refund
from app.payments.webhooks import WebhookEvent, WebhookType

logger = logging.getLogger(__name__)


class BookingNotPayableError(ConflictError):
    code = "booking_not_payable"


async def start_payment(
    session: AsyncSession, provider: PaymentProvider, guest: Principal, booking_id: UUID
) -> Payment:
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
        )
    except PaymentProviderError as exc:
        raise ServiceUnavailableError("The payment provider is unavailable. Try again.") from exc
    payment.provider_payment_id = created.id
    payment.checkout_url = created.checkout_url
    return payment


async def handle_webhook(session: AsyncSession, event: WebhookEvent) -> None:
    first_delivery = await session.scalar(
        insert(ProcessedWebhook)
        .values(event_id=event.id, event_type=event.type)
        .on_conflict_do_nothing()
        .returning(ProcessedWebhook.event_id)
    )
    if first_delivery is None:
        logger.info("Webhook %s already processed", event.id)
        return

    if event.type in (WebhookType.PAYMENT_SUCCEEDED, WebhookType.PAYMENT_FAILED):
        await _on_payment_event(session, event)
    else:
        await _on_refund_event(session, event)


async def _on_payment_event(session: AsyncSession, event: WebhookEvent) -> None:
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
        await schedule_refund(session, booking, payment.amount)


async def _on_refund_event(session: AsyncSession, event: WebhookEvent) -> None:
    refund = await session.scalar(
        select(Refund).where(Refund.id == event.data.reference).with_for_update()
    )
    if refund is None:
        logger.warning("Webhook %s refers to unknown refund %s", event.id, event.data.reference)
        return
    refund.provider_refund_id = refund.provider_refund_id or event.data.id
    refund.status = (
        RefundStatus.SUCCEEDED
        if event.type is WebhookType.REFUND_SUCCEEDED
        else RefundStatus.FAILED
    )


async def submit_pending_refunds(
    sessions: async_sessionmaker[AsyncSession], provider: PaymentProvider, limit: int = 20
) -> int:
    """Send recorded refunds to the provider. Safe to retry: the refund id is the
    idempotency key, so the provider never pays the same refund twice."""
    submitted = 0
    async with sessions.begin() as session:
        rows = (
            await session.execute(
                select(Refund, Payment)
                .join(Payment, Payment.id == Refund.payment_id)
                .where(Refund.status == RefundStatus.PENDING)
                .order_by(Refund.created_at)
                .limit(limit)
                .with_for_update(of=Refund, skip_locked=True)
            )
        ).all()
        for refund, payment in rows:
            if payment.provider_payment_id is None:  # pragma: no cover - paid payments have one
                continue
            try:
                refund.provider_refund_id = await provider.create_refund(
                    payment_id=payment.provider_payment_id,
                    amount=refund.amount,
                    reference=str(refund.id),
                    idempotency_key=str(refund.id),
                )
            except PaymentProviderError:
                refund.attempts += 1
                logger.warning("Refund %s not submitted, will retry", refund.id, exc_info=True)
                break
            refund.status = RefundStatus.SUBMITTED
            submitted += 1
    return submitted
