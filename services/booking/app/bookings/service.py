"""Booking lifecycle. Every status change goes through `_transition`.

pending_payment -> confirmed   (payment succeeded)
pending_payment -> expired     (hold ran out, dates released)
pending_payment -> cancelled   (guest gave up before paying)
confirmed       -> cancelled   (guest or host; refund by policy)
confirmed       -> completed   (after check-out)
"""

import uuid
from collections.abc import Sequence
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
from app.bookings.models import Booking, BookingStatus
from app.bookings.policy import refund_amount
from app.bookings.schemas import BookingIn
from app.errors import ConflictError, DomainError, NotFoundError
from app.outbox import outbox_add
from app.payments.refunds import schedule_refund

S = BookingStatus

TRANSITIONS: dict[str, set[str]] = {
    S.PENDING_PAYMENT: {S.CONFIRMED, S.EXPIRED, S.CANCELLED},
    S.CONFIRMED: {S.CANCELLED, S.COMPLETED},
    S.CANCELLED: set(),
    S.EXPIRED: set(),
    S.COMPLETED: set(),
}


class InvalidStateTransitionError(ConflictError):
    code = "invalid_state_transition"


def _transition(booking: Booking, target: BookingStatus) -> None:
    if target not in TRANSITIONS[booking.status]:
        raise InvalidStateTransitionError(
            f"A booking cannot go from '{booking.status}' to '{target}'."
        )
    booking.status = target
    if target is not S.PENDING_PAYMENT:
        booking.hold_expires_at = None


async def create_booking(
    session: AsyncSession, guest: Principal, data: BookingIn, hold: timedelta
) -> Booking:
    listing, pricing, stay = await price_available_stay(
        session, data.listing_id, data.check_in, data.check_out, data.guests, lock=True
    )
    if listing.host_id == guest.user_id:
        raise DomainError("You cannot book your own listing.")
    # Stale holds still occupy dates in the exclusion constraint until they are expired.
    await expire_stale_holds(session, listing_id=listing.id)

    booking = Booking(
        listing_id=listing.id,
        guest_id=guest.user_id,
        host_id=listing.host_id,
        period=Range(data.check_in, data.check_out),
        guests=data.guests,
        status=S.PENDING_PAYMENT,
        currency=pricing.currency,
        subtotal=stay.subtotal,
        discount=stay.discount,
        cleaning_fee=stay.cleaning_fee,
        total=stay.total,
        hold_expires_at=datetime.now(UTC) + hold,
    )
    session.add(booking)
    try:
        await session.flush()
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == EXCLUSION_VIOLATION:
            raise DatesUnavailableError("Some of the selected nights were just booked.") from exc
        raise
    await session.refresh(booking)
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


async def list_guest_bookings(session: AsyncSession, guest: Principal) -> Sequence[Booking]:
    stmt = (
        select(Booking)
        .where(Booking.guest_id == guest.user_id)
        .order_by(Booking.created_at.desc())
        .limit(100)
    )
    return (await session.scalars(stmt)).all()


async def list_host_bookings(
    session: AsyncSession, host: Principal, listing_id: UUID | None
) -> Sequence[Booking]:
    stmt = select(Booking).where(
        Booking.host_id == host.user_id,
        Booking.status.in_((S.CONFIRMED, S.PENDING_PAYMENT, S.COMPLETED)),
    )
    if listing_id is not None:
        stmt = stmt.where(Booking.listing_id == listing_id)
    stmt = stmt.order_by(func.lower(Booking.period)).limit(200)
    return (await session.scalars(stmt)).all()


async def cancel_booking(
    session: AsyncSession,
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
        await schedule_refund(session, booking, amount)
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
    stmt = update(Booking).where(
        Booking.status == S.PENDING_PAYMENT, Booking.hold_expires_at <= func.now()
    )
    if listing_id is not None:
        stmt = stmt.where(Booking.listing_id == listing_id)
    result = cast(
        CursorResult[Any],
        await session.execute(stmt.values(status=S.EXPIRED, hold_expires_at=None)),
    )
    return result.rowcount


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
