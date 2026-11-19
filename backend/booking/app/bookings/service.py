"""Booking lifecycle. Every status change goes through `_transition`.

Instant booking starts at pending_payment. A place without it starts at awaiting_host:

awaiting_host   -> pending_payment (host accepted; the guest has a day to pay)
awaiting_host   -> declined        (host declined)
awaiting_host   -> expired         (host did not answer in time, dates released)
awaiting_host   -> cancelled       (guest withdrew the request)
pending_payment -> confirmed   (payment succeeded)
pending_payment -> expired     (hold ran out, dates released)
pending_payment -> cancelled   (guest gave up before paying)
confirmed       -> cancelled   (guest or host; refund by policy)
confirmed       -> completed   (after check-out)
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from contracts import BookingEvent, BookingEventType, BookingSnapshot, CancelledBy
from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal
from app.availability.service import (
    EXCLUSION_VIOLATION,
    DatesUnavailableError,
    price_available_stay,
    today,
)
from app.bookings.models import HOLDING_STATUSES, Booking, BookingMessage, BookingStatus
from app.bookings.policy import refund_amount
from app.bookings.schemas import BookingIn
from app.errors import ConflictError, DomainError, NotFoundError
from app.metrics import BOOKING_STATUS_CHANGES
from app.outbox import outbox_add
from app.pagination import count
from app.payments.provider import PaymentProvider
from app.payments.refunds import refund_booking

S = BookingStatus

TRANSITIONS: dict[str, set[str]] = {
    S.AWAITING_HOST: {S.PENDING_PAYMENT, S.DECLINED, S.EXPIRED, S.CANCELLED},
    S.PENDING_PAYMENT: {S.CONFIRMED, S.EXPIRED, S.CANCELLED},
    S.CONFIRMED: {S.CANCELLED, S.COMPLETED},
    S.CANCELLED: set(),
    S.EXPIRED: set(),
    S.COMPLETED: set(),
    S.DECLINED: set(),
}


class InvalidStateTransitionError(ConflictError):
    code = "invalid_state_transition"


def _transition(booking: Booking, target: BookingStatus) -> None:
    if target not in TRANSITIONS[booking.status]:
        raise InvalidStateTransitionError(
            f"A booking cannot go from '{booking.status}' to '{target}'."
        )
    booking.status = target
    if target not in HOLDING_STATUSES:
        booking.hold_expires_at = None
    BOOKING_STATUS_CHANGES.labels(target).inc()


async def create_booking(
    session: AsyncSession,
    guest: Principal,
    data: BookingIn,
    hold: timedelta,
    request_window: timedelta,
) -> Booking:
    """Holds the dates: for `hold` until the payment or, when the host accepts bookings
    first, for `request_window` until the host's answer."""
    listing, pricing, stay = await price_available_stay(
        session, data.listing_id, data.check_in, data.check_out, data.guests, lock=True
    )
    if listing.host_id == guest.user_id:
        raise DomainError("You cannot book your own listing.")
    # Stale holds still occupy dates in the exclusion constraint until they are expired.
    await expire_stale_holds(session, listing_id=listing.id)

    status = S.PENDING_PAYMENT if pricing.instant_book else S.AWAITING_HOST
    booking = Booking(
        listing_id=listing.id,
        guest_id=guest.user_id,
        host_id=listing.host_id,
        period=Range(data.check_in, data.check_out),
        guests=data.guests,
        status=status,
        currency=pricing.currency,
        subtotal=stay.subtotal,
        discount=stay.discount,
        cleaning_fee=stay.cleaning_fee,
        total=stay.total,
        hold_expires_at=datetime.now(UTC) + (hold if pricing.instant_book else request_window),
    )
    session.add(booking)
    try:
        await session.flush()
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == EXCLUSION_VIOLATION:
            raise DatesUnavailableError("Some of the selected nights were just booked.") from exc
        raise
    await session.refresh(booking)
    BOOKING_STATUS_CHANGES.labels(status).inc()
    if status is S.AWAITING_HOST:
        _emit(session, booking, BookingEventType.REQUESTED)  # tells the host by email
    return booking


async def get_booking(
    session: AsyncSession, principal: Principal, booking_id: UUID, *, as_host: bool = False
) -> Booking:
    """A booking is visible to its guest and its host only."""
    owner = Booking.host_id if as_host else Booking.guest_id
    booking = await session.scalar(
        select(Booking).where(Booking.id == booking_id, owner == principal.user_id)
    )
    if booking is None:
        raise NotFoundError("Booking not found.")
    return booking


async def list_messages(
    session: AsyncSession, principal: Principal, booking_id: UUID, *, as_host: bool
) -> tuple[Booking, list[BookingMessage]]:
    """The conversation about a booking, oldest first. Only its guest and host see it."""
    booking = await get_booking(session, principal, booking_id, as_host=as_host)
    messages = await session.scalars(
        select(BookingMessage)
        .where(BookingMessage.booking_id == booking.id)
        .order_by(BookingMessage.created_at)
    )
    return booking, list(messages)


async def send_message(
    session: AsyncSession, principal: Principal, booking_id: UUID, text: str, *, as_host: bool
) -> tuple[Booking, BookingMessage]:
    booking = await get_booking(session, principal, booking_id, as_host=as_host)
    message = BookingMessage(booking_id=booking.id, author_id=principal.user_id, text=text)
    session.add(message)
    await session.flush()
    await session.refresh(message)  # created_at comes from the database
    return booking, message


async def list_guest_bookings(
    session: AsyncSession, guest: Principal, limit: int, offset: int
) -> tuple[list[Booking], int]:
    """Newest first."""
    stmt = select(Booking).where(Booking.guest_id == guest.user_id)
    page = stmt.order_by(Booking.created_at.desc()).limit(limit).offset(offset)
    return list((await session.scalars(page)).all()), await count(session, stmt)


async def list_host_bookings(
    session: AsyncSession,
    host: Principal,
    listing_id: UUID | None,
    status: BookingStatus | None,
    upcoming: bool,
    limit: int,
    offset: int,
) -> tuple[list[Booking], int]:
    """By check-in date. `upcoming` leaves out stays that are already over."""
    shown = (S.AWAITING_HOST, S.PENDING_PAYMENT, S.CONFIRMED, S.COMPLETED)
    stmt = select(Booking).where(
        Booking.host_id == host.user_id,
        Booking.status.in_([status] if status else shown),
    )
    if listing_id is not None:
        stmt = stmt.where(Booking.listing_id == listing_id)
    if upcoming:
        stmt = stmt.where(func.upper(Booking.period) > today())
    page = stmt.order_by(func.lower(Booking.period), Booking.id).limit(limit).offset(offset)
    return list((await session.scalars(page)).all()), await count(session, stmt)


async def _host_request(session: AsyncSession, host: Principal, booking_id: UUID) -> Booking:
    """The host's booking request, locked, while it can still be answered."""
    booking = await session.scalar(
        select(Booking)
        .where(Booking.id == booking_id, Booking.host_id == host.user_id)
        .with_for_update()
    )
    if booking is None:
        raise NotFoundError("Booking not found.")
    if booking.status != S.AWAITING_HOST:
        raise InvalidStateTransitionError(f"A '{booking.status}' booking is not a request.")
    # The sweeper may not have run yet; a late answer must not revive the request.
    if booking.hold_expires_at is not None and booking.hold_expires_at <= datetime.now(UTC):
        raise InvalidStateTransitionError("The request has expired.")
    return booking


async def accept_request(
    session: AsyncSession, host: Principal, booking_id: UUID, pay_window: timedelta
) -> Booking:
    booking = await _host_request(session, host, booking_id)
    _transition(booking, S.PENDING_PAYMENT)
    booking.hold_expires_at = datetime.now(UTC) + pay_window  # the dates stay held
    _emit(session, booking, BookingEventType.ACCEPTED)
    return booking


async def decline_request(
    session: AsyncSession, host: Principal, booking_id: UUID, reason: str
) -> Booking:
    booking = await _host_request(session, host, booking_id)
    _transition(booking, S.DECLINED)  # releases the dates
    booking.cancelled_by = CancelledBy.HOST
    booking.cancellation_reason = reason
    _emit(session, booking, BookingEventType.DECLINED)
    return booking


async def cancel_booking(
    session: AsyncSession,
    provider: PaymentProvider,
    principal: Principal,
    booking_id: UUID,
    reason: str,
    by: CancelledBy,
) -> Booking:
    owner = Booking.host_id if by is CancelledBy.HOST else Booking.guest_id
    booking = await session.scalar(
        select(Booking)
        .where(Booking.id == booking_id, owner == principal.user_id)
        .with_for_update()
    )
    if booking is None:
        raise NotFoundError("Booking not found.")
    if booking.check_in < today():
        raise InvalidStateTransitionError("The stay has already started.")

    was_confirmed = booking.status == S.CONFIRMED
    _transition(booking, S.CANCELLED)
    booking.cancelled_by = by
    booking.cancellation_reason = reason
    if was_confirmed:
        amount = refund_amount(
            total=booking.total, check_in=booking.check_in, today=today(), cancelled_by=by
        )
        await refund_booking(session, provider, booking, amount)
        _emit(session, booking, BookingEventType.CANCELLED)
    return booking


async def confirm_paid_booking(session: AsyncSession, booking: Booking) -> bool:
    """Returns False if the booking can no longer be confirmed (expired or cancelled)."""
    if booking.status != S.PENDING_PAYMENT:
        return False
    # Even with the hold past its time, the dates are still ours until the hold is expired.
    _transition(booking, S.CONFIRMED)
    _emit(session, booking, BookingEventType.CONFIRMED)
    return True


async def expire_stale_holds(session: AsyncSession, *, listing_id: UUID | None = None) -> int:
    """Releases the dates of unpaid bookings and unanswered requests whose time is up."""
    unpaid = update(Booking).where(
        Booking.status == S.PENDING_PAYMENT, Booking.hold_expires_at <= func.now()
    )
    unanswered = update(Booking).where(
        Booking.status == S.AWAITING_HOST, Booking.hold_expires_at <= func.now()
    )
    if listing_id is not None:
        unpaid = unpaid.where(Booking.listing_id == listing_id)
        unanswered = unanswered.where(Booking.listing_id == listing_id)
    expired = {"status": S.EXPIRED, "hold_expires_at": None}

    result = cast(CursorResult[Any], await session.execute(unpaid.values(expired)))
    # RETURNING gives the expired requests back, so each guest can be told by email.
    requests = (await session.scalars(unanswered.values(expired).returning(Booking))).all()
    for booking in requests:
        _emit(session, booking, BookingEventType.REQUEST_EXPIRED)
    return result.rowcount + len(requests)


async def complete_finished_stays(session: AsyncSession, limit: int = 100) -> int:
    finished = (
        await session.scalars(
            select(Booking)
            .where(Booking.status == S.CONFIRMED, func.upper(Booking.period) <= today())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).all()
    for booking in finished:
        _transition(booking, S.COMPLETED)
        _emit(session, booking, BookingEventType.COMPLETED)
    return len(finished)


def _emit(session: AsyncSession, booking: Booking, event_type: BookingEventType) -> None:
    outbox_add(
        session,
        BookingEvent(
            event_id=uuid.uuid4(),
            event_type=event_type,
            occurred_at=datetime.now(UTC),
            booking=BookingSnapshot(
                id=booking.id,
                listing_id=booking.listing_id,
                guest_id=booking.guest_id,
                host_id=booking.host_id,
                check_in=booking.check_in,
                check_out=booking.check_out,
                guests=booking.guests,
                currency=booking.currency,
                total=booking.total,
                refund=booking.refund_amount,
                cancelled_by=CancelledBy(booking.cancelled_by) if booking.cancelled_by else None,
            ),
        ),
    )
