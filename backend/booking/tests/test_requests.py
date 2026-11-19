"""Places that are not instantly bookable: every booking is a request the host answers."""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import Database
from app.jobs import BackgroundJobs
from app.listings.models import Listing
from tests.factories import PRICING
from tests.helpers import Headers, book, outbox_events, send_webhook
from tests.test_payments import pay


@pytest.fixture
async def request_listing(client: AsyncClient, priced_listing: Listing, auth: Headers) -> Listing:
    response = await client.put(
        f"/api/v1/host/listings/{priced_listing.id}/pricing",
        json=PRICING | {"instant_book": False},
        headers=auth(priced_listing.host_id, "host"),
    )
    assert response.json()["instant_book"] is False
    return priced_listing


async def answer(
    client: AsyncClient, auth: Headers, booking: dict[str, Any], action: str
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/host/bookings/{booking['id']}/{action}",
        json={"reason": "Sorry, we are renovating."} if action == "decline" else None,
        headers=auth(booking["host_id"], "host"),
    )
    assert response.status_code == 200, response.text
    data: dict[str, Any] = response.json()
    return data


async def free_nights(client: AsyncClient, listing: Listing, start: date) -> list[bool]:
    calendar = await client.get(
        f"/api/v1/listings/{listing.id}/calendar",
        params={"start_date": str(start), "end_date": str(start + timedelta(3))},
    )
    return [day["available"] for day in calendar.json()["days"]]


async def test_accepted_request_is_paid_and_confirmed(
    client: AsyncClient, request_listing: Listing, auth: Headers, next_monday: date, db: Database
) -> None:
    created = await book(client, auth(uuid4()), request_listing, next_monday)
    request = created.json()

    assert created.status_code == 201, created.text
    assert request["status"] == "awaiting_host"
    answer_by = datetime.fromisoformat(request["hold_expires_at"]) - datetime.now(UTC)
    assert timedelta(hours=23) < answer_by <= timedelta(hours=24)
    assert await free_nights(client, request_listing, next_monday) == [False, False, False]

    # Nothing to pay until the host has said yes.
    early = await client.post(
        f"/api/v1/bookings/{request['id']}/payments", headers=auth(request["guest_id"])
    )
    assert early.status_code == 409

    waiting = await client.get(
        "/api/v1/host/bookings",
        params={"status": "awaiting_host"},
        headers=auth(request["host_id"], "host"),
    )
    assert [b["id"] for b in waiting.json()["items"]] == [request["id"]]

    accepted = await answer(client, auth, request, "accept")
    assert accepted["status"] == "pending_payment"
    pay_by = datetime.fromisoformat(accepted["hold_expires_at"]) - datetime.now(UTC)
    assert timedelta(hours=23) < pay_by <= timedelta(hours=24)

    payment = await pay(client, auth, request)
    await send_webhook(client, "payment.succeeded", payment["id"], payment["amount"])
    booking = await client.get(
        f"/api/v1/bookings/{request['id']}", headers=auth(request["guest_id"])
    )
    assert booking.json()["status"] == "confirmed"

    events = [e["event_type"] for e in await outbox_events(db)]
    assert events == ["booking.requested", "booking.accepted", "booking.confirmed"]


async def test_declined_request_frees_the_dates(
    client: AsyncClient, request_listing: Listing, auth: Headers, next_monday: date, db: Database
) -> None:
    request = (await book(client, auth(uuid4()), request_listing, next_monday)).json()

    declined = await answer(client, auth, request, "decline")

    assert declined["status"] == "declined"
    assert declined["cancelled_by"] == "host"
    assert await free_nights(client, request_listing, next_monday) == [True, True, True]
    assert (await book(client, auth(uuid4()), request_listing, next_monday)).status_code == 201
    assert [e["event_type"] for e in await outbox_events(db)][1] == "booking.declined"


async def test_unanswered_request_expires(
    client: AsyncClient, request_listing: Listing, auth: Headers, next_monday: date, db: Database
) -> None:
    request = (await book(client, auth(uuid4()), request_listing, next_monday)).json()
    async with db.engine.begin() as connection:
        await connection.execute(text("UPDATE bookings SET hold_expires_at = now()"))

    # Too late, even before the sweeper has run.
    late = await client.post(
        f"/api/v1/host/bookings/{request['id']}/accept", headers=auth(request["host_id"], "host")
    )
    assert late.status_code == 409

    async def publish(*_: Any) -> None:
        return None

    assert await BackgroundJobs(db, publish).expire_holds() == 1
    fetched = await client.get(
        f"/api/v1/bookings/{request['id']}", headers=auth(request["guest_id"])
    )
    assert fetched.json()["status"] == "expired"
    assert [e["event_type"] for e in await outbox_events(db)][-1] == "booking.request_expired"


async def test_only_the_host_answers_and_only_once(
    client: AsyncClient, request_listing: Listing, auth: Headers, next_monday: date
) -> None:
    request = (await book(client, auth(uuid4()), request_listing, next_monday)).json()
    url = f"/api/v1/host/bookings/{request['id']}/accept"

    other_host = await client.post(url, headers=auth(uuid4(), "host"))
    guest = await client.post(url, headers=auth(request["guest_id"]))
    assert other_host.status_code == 404
    assert guest.status_code == 403

    await answer(client, auth, request, "accept")
    again = await client.post(url, headers=auth(request["host_id"], "host"))
    assert again.status_code == 409
    assert again.json()["code"] == "invalid_state_transition"


async def test_guest_can_withdraw_a_request(
    client: AsyncClient, request_listing: Listing, auth: Headers, next_monday: date
) -> None:
    request = (await book(client, auth(uuid4()), request_listing, next_monday)).json()

    cancelled = await client.post(
        f"/api/v1/bookings/{request['id']}/cancel", json={}, headers=auth(request["guest_id"])
    )

    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["refund_amount"] == 0
    assert await free_nights(client, request_listing, next_monday) == [True, True, True]


async def test_instant_book_is_the_default(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> None:
    calendar = await client.get(
        f"/api/v1/listings/{priced_listing.id}/calendar",
        params={"start_date": str(next_monday), "end_date": str(next_monday + timedelta(1))},
    )
    booking = (await book(client, auth(uuid4()), priced_listing, next_monday)).json()

    assert calendar.json()["instant_book"] is True
    assert booking["status"] == "pending_payment"
