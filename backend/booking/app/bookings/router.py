from datetime import timedelta
from typing import Annotated
from uuid import UUID

from contracts import CancelledBy
from fastapi import APIRouter, Depends, Request, status

from app.auth import HostDep, Principal, current_principal
from app.bookings import service
from app.bookings.models import BookingStatus
from app.bookings.schemas import (
    BookingIn,
    BookingOut,
    CancelIn,
    MessageIn,
    MessageOut,
    PaymentOut,
)
from app.db import SessionDep
from app.pagination import Limit, Offset, Page
from app.payments import service as payments
from app.payments.provider import ProviderDep
from app.ratelimit import limit_per_user

UserDep = Annotated[Principal, Depends(current_principal)]
# Writes are limited per account: they lock rows and call the payment provider.
WRITE_LIMIT = [Depends(limit_per_user("booking"))]

guest_router = APIRouter(prefix="/api/v1/bookings", tags=["bookings"])


@guest_router.post("", status_code=status.HTTP_201_CREATED, dependencies=WRITE_LIMIT)
async def create_booking(
    request: Request, session: SessionDep, guest: UserDep, body: BookingIn
) -> BookingOut:
    """Hold the dates for a limited time; pay before `hold_expires_at` to confirm.

    If the place is not instantly bookable, the booking is a request (`awaiting_host`):
    the host has until `hold_expires_at` to accept it, and the guest pays after that.
    """
    settings = request.app.state.settings
    booking = await service.create_booking(
        session,
        guest,
        body,
        hold=timedelta(minutes=settings.hold_minutes),
        request_window=timedelta(hours=settings.request_hours),
    )
    return BookingOut.from_model(booking)


@guest_router.get("")
async def list_my_bookings(
    session: SessionDep, guest: UserDep, limit: Limit = 20, offset: Offset = 0
) -> Page[BookingOut]:
    """Newest first."""
    bookings, total = await service.list_guest_bookings(session, guest, limit, offset)
    items = [BookingOut.from_model(b) for b in bookings]
    return Page(items=items, total=total, limit=limit, offset=offset)


@guest_router.get("/{booking_id}")
async def get_my_booking(session: SessionDep, guest: UserDep, booking_id: UUID) -> BookingOut:
    return BookingOut.from_model(await service.get_booking(session, guest, booking_id))


@guest_router.post(
    "/{booking_id}/payments", status_code=status.HTTP_201_CREATED, dependencies=WRITE_LIMIT
)
async def pay_for_booking(
    request: Request, session: SessionDep, guest: UserDep, provider: ProviderDep, booking_id: UUID
) -> PaymentOut:
    """Start a payment and get the provider's checkout page for the guest.

    After paying, the provider sends the guest back to the booking's page on the website.
    Asking again while the payment is open returns the same checkout page.
    """
    return_url = f"{request.app.state.settings.site_url}/bookings/{booking_id}"
    payment = await payments.start_payment(session, provider, guest, booking_id, return_url)
    return PaymentOut.from_model(payment)


@guest_router.post("/{booking_id}/cancel", dependencies=WRITE_LIMIT)
async def cancel_my_booking(
    session: SessionDep, guest: UserDep, provider: ProviderDep, booking_id: UUID, body: CancelIn
) -> BookingOut:
    """Full refund 7+ days before check-in, half up to the day before, none on the day."""
    booking = await service.cancel_booking(
        session, provider, guest, booking_id, body.reason, CancelledBy.GUEST
    )
    return BookingOut.from_model(booking)


@guest_router.get("/{booking_id}/messages")
async def guest_messages(session: SessionDep, guest: UserDep, booking_id: UUID) -> list[MessageOut]:
    """The conversation with the host, oldest first."""
    booking, messages = await service.list_messages(session, guest, booking_id, as_host=False)
    return [MessageOut.from_model(m, booking) for m in messages]


@guest_router.post(
    "/{booking_id}/messages", status_code=status.HTTP_201_CREATED, dependencies=WRITE_LIMIT
)
async def write_to_host(
    session: SessionDep, guest: UserDep, booking_id: UUID, body: MessageIn
) -> MessageOut:
    booking, message = await service.send_message(
        session, guest, booking_id, body.text, as_host=False
    )
    return MessageOut.from_model(message, booking)


host_router = APIRouter(prefix="/api/v1/host/bookings", tags=["host: bookings"])


@host_router.get("")
async def list_host_bookings(
    session: SessionDep,
    host: HostDep,
    listing_id: UUID | None = None,
    status: BookingStatus | None = None,
    upcoming: bool = False,
    limit: Limit = 20,
    offset: Offset = 0,
) -> Page[BookingOut]:
    """Requests, upcoming, current and past stays at the host's listings, by check-in date.

    `status=awaiting_host` lists only the requests waiting for an answer;
    `upcoming=true` leaves out the stays that are over.
    """
    bookings, total = await service.list_host_bookings(
        session, host, listing_id, status, upcoming, limit, offset
    )
    items = [BookingOut.from_model(b) for b in bookings]
    return Page(items=items, total=total, limit=limit, offset=offset)


@host_router.get("/{booking_id}")
async def get_host_booking(session: SessionDep, host: HostDep, booking_id: UUID) -> BookingOut:
    booking = await service.get_booking(session, host, booking_id, as_host=True)
    return BookingOut.from_model(booking)


@host_router.post("/{booking_id}/accept", dependencies=WRITE_LIMIT)
async def accept_request(
    request: Request, session: SessionDep, host: HostDep, booking_id: UUID
) -> BookingOut:
    """Accept a request; the guest then has `accepted_pay_hours` to pay for it."""
    pay_window = timedelta(hours=request.app.state.settings.accepted_pay_hours)
    booking = await service.accept_request(session, host, booking_id, pay_window)
    return BookingOut.from_model(booking)


@host_router.post("/{booking_id}/decline", dependencies=WRITE_LIMIT)
async def decline_request(
    session: SessionDep, host: HostDep, booking_id: UUID, body: CancelIn
) -> BookingOut:
    """Decline a request; its dates become free again."""
    booking = await service.decline_request(session, host, booking_id, body.reason)
    return BookingOut.from_model(booking)


@host_router.post("/{booking_id}/cancel", dependencies=WRITE_LIMIT)
async def cancel_as_host(
    session: SessionDep, host: HostDep, provider: ProviderDep, booking_id: UUID, body: CancelIn
) -> BookingOut:
    """The guest always gets a full refund when the host cancels."""
    booking = await service.cancel_booking(
        session, provider, host, booking_id, body.reason, CancelledBy.HOST
    )
    return BookingOut.from_model(booking)


@host_router.get("/{booking_id}/messages")
async def host_messages(session: SessionDep, host: HostDep, booking_id: UUID) -> list[MessageOut]:
    """The conversation with the guest, oldest first."""
    booking, messages = await service.list_messages(session, host, booking_id, as_host=True)
    return [MessageOut.from_model(m, booking) for m in messages]


@host_router.post(
    "/{booking_id}/messages", status_code=status.HTTP_201_CREATED, dependencies=WRITE_LIMIT
)
async def write_to_guest(
    session: SessionDep, host: HostDep, booking_id: UUID, body: MessageIn
) -> MessageOut:
    booking, message = await service.send_message(
        session, host, booking_id, body.text, as_host=True
    )
    return MessageOut.from_model(message, booking)
