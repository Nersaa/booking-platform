from datetime import timedelta
from typing import Annotated
from uuid import UUID

from contracts import CancelledBy
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app import idempotency
from app.auth import HostDep, Principal, current_principal
from app.bookings import service
from app.bookings.schemas import BookingIn, BookingOut, CancelIn, PaymentOut
from app.db import SessionDep
from app.idempotency import IdempotencyKeyHeader
from app.payments import service as payments
from app.payments.provider import PaymentProvider

UserDep = Annotated[Principal, Depends(current_principal)]


def _provider(request: Request) -> PaymentProvider:
    provider: PaymentProvider = request.app.state.payments
    return provider


ProviderDep = Annotated[PaymentProvider, Depends(_provider)]

guest_router = APIRouter(prefix="/api/v1/bookings", tags=["bookings"])


@guest_router.post("", status_code=status.HTTP_201_CREATED, response_model=BookingOut)
async def create_booking(
    request: Request,
    session: SessionDep,
    guest: UserDep,
    body: BookingIn,
    key: IdempotencyKeyHeader,
) -> JSONResponse:
    """Hold the dates for a limited time; pay before `hold_expires_at` to confirm."""
    hold = timedelta(minutes=request.app.state.settings.hold_minutes)

    async def create() -> BookingOut:
        return BookingOut.from_model(await service.create_booking(session, guest, body, hold))

    return await idempotency.respond(
        session,
        user_id=guest.user_id,
        key=key,
        operation="create_booking",
        payload=body.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
        action=create,
    )


@guest_router.get("")
async def list_my_bookings(session: SessionDep, guest: UserDep) -> list[BookingOut]:
    return [BookingOut.from_model(b) for b in await service.list_guest_bookings(session, guest)]


@guest_router.get("/{booking_id}")
async def get_my_booking(session: SessionDep, guest: UserDep, booking_id: UUID) -> BookingOut:
    return BookingOut.from_model(await service.get_booking(session, guest, booking_id))


@guest_router.post(
    "/{booking_id}/payments", status_code=status.HTTP_201_CREATED, response_model=PaymentOut
)
async def pay_for_booking(
    session: SessionDep,
    guest: UserDep,
    provider: ProviderDep,
    booking_id: UUID,
    key: IdempotencyKeyHeader,
) -> JSONResponse:
    """Start a payment and get the provider's checkout page for the guest."""

    async def pay() -> PaymentOut:
        payment = await payments.start_payment(session, provider, guest, booking_id)
        return PaymentOut.from_model(payment)

    return await idempotency.respond(
        session,
        user_id=guest.user_id,
        key=key,
        operation="pay_for_booking",
        payload={"booking_id": str(booking_id)},
        status_code=status.HTTP_201_CREATED,
        action=pay,
    )


@guest_router.post("/{booking_id}/cancel", response_model=BookingOut)
async def cancel_my_booking(
    session: SessionDep,
    guest: UserDep,
    booking_id: UUID,
    body: CancelIn,
    key: IdempotencyKeyHeader,
) -> JSONResponse:
    """Full refund 7+ days before check-in, half up to the day before, none on the day."""

    async def cancel() -> BookingOut:
        booking = await service.cancel_booking(
            session, guest, booking_id, body.reason, CancelledBy.GUEST
        )
        return BookingOut.from_model(booking)

    return await idempotency.respond(
        session,
        user_id=guest.user_id,
        key=key,
        operation="cancel_booking",
        payload={"booking_id": str(booking_id), **body.model_dump()},
        status_code=status.HTTP_200_OK,
        action=cancel,
    )


host_router = APIRouter(prefix="/api/v1/host/bookings", tags=["host: bookings"])


@host_router.get("")
async def list_host_bookings(
    session: SessionDep, host: HostDep, listing_id: UUID | None = None
) -> list[BookingOut]:
    """Upcoming, current and past stays at the host's listings."""
    bookings = await service.list_host_bookings(session, host, listing_id)
    return [BookingOut.from_model(b) for b in bookings]


@host_router.get("/{booking_id}")
async def get_host_booking(session: SessionDep, host: HostDep, booking_id: UUID) -> BookingOut:
    booking = await service.get_booking(session, host, booking_id, as_host=True)
    return BookingOut.from_model(booking)


@host_router.post("/{booking_id}/cancel", response_model=BookingOut)
async def cancel_as_host(
    session: SessionDep,
    host: HostDep,
    booking_id: UUID,
    body: CancelIn,
    key: IdempotencyKeyHeader,
) -> JSONResponse:
    """The guest always gets a full refund when the host cancels."""

    async def cancel() -> BookingOut:
        booking = await service.cancel_booking(
            session, host, booking_id, body.reason, CancelledBy.HOST
        )
        return BookingOut.from_model(booking)

    return await idempotency.respond(
        session,
        user_id=host.user_id,
        key=key,
        operation="host_cancel_booking",
        payload={"booking_id": str(booking_id), **body.model_dump()},
        status_code=status.HTTP_200_OK,
        action=cancel,
    )
