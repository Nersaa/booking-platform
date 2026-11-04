import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy import text

from app.db import Database
from app.listings.models import Listing
from tests.helpers import Headers, book


async def test_booking_holds_dates_at_the_quoted_price(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> None:
    guest = auth(uuid4())
    quote = await client.get(
        f"/api/v1/listings/{priced_listing.id}/quote",
        params={"check_in": str(next_monday), "check_out": str(next_monday + timedelta(3))},
    )

    response = await book(client, guest, priced_listing, next_monday, nights=3)

    assert response.status_code == 201, response.text
    booking = response.json()
    assert booking["status"] == "pending_payment"
    assert booking["total"] == quote.json()["total"]
    assert booking["host_id"] == str(priced_listing.host_id)
    hold = datetime.fromisoformat(booking["hold_expires_at"]) - datetime.now(UTC)
    assert timedelta(minutes=14) < hold <= timedelta(minutes=15)

    calendar = await client.get(
        f"/api/v1/listings/{priced_listing.id}/calendar",
        params={"start_date": str(next_monday), "end_date": str(next_monday + timedelta(4))},
    )
    assert [d["available"] for d in calendar.json()["days"]] == [False, False, False, True]


async def test_overlapping_booking_is_rejected(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> None:
    await book(client, auth(uuid4()), priced_listing, next_monday, nights=3)

    overlap = await book(client, auth(uuid4()), priced_listing, next_monday + timedelta(2))
    back_to_back = await book(client, auth(uuid4()), priced_listing, next_monday + timedelta(3))

    assert overlap.status_code == 409
    assert overlap.json()["code"] == "dates_unavailable"
    assert back_to_back.status_code == 201, "check-out day can be the next check-in day"


async def test_concurrent_requests_for_the_same_dates_produce_one_booking(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> None:
    responses = await asyncio.gather(
        *(book(client, auth(uuid4()), priced_listing, next_monday) for _ in range(8))
    )

    statuses = sorted(r.status_code for r in responses)
    assert statuses == [201] + [409] * 7


async def test_idempotency_key_replays_the_first_response(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> None:
    guest = auth(uuid4())

    first = await book(client, guest, priced_listing, next_monday, idempotency_key="retry-me-1")
    retry = await book(client, guest, priced_listing, next_monday, idempotency_key="retry-me-1")
    reused = await book(
        client, guest, priced_listing, next_monday + timedelta(10), idempotency_key="retry-me-1"
    )

    assert first.status_code == retry.status_code == 201
    assert retry.json()["id"] == first.json()["id"]
    assert retry.headers["idempotent-replayed"] == "true"
    assert reused.status_code == 422
    assert reused.json()["code"] == "idempotency_key_reused"


async def test_concurrent_retries_with_one_key_create_one_booking(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> None:
    guest = auth(uuid4())

    responses = await asyncio.gather(
        *(
            book(client, guest, priced_listing, next_monday, idempotency_key="double-click")
            for _ in range(4)
        )
    )

    assert {r.status_code for r in responses} == {201}
    assert len({r.json()["id"] for r in responses}) == 1


async def test_failed_request_does_not_burn_the_key(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> None:
    guest = auth(uuid4())
    too_many_guests = await book(
        client, guest, priced_listing, next_monday, guests=9, idempotency_key="key-after-error"
    )
    fixed = await book(
        client, guest, priced_listing, next_monday, idempotency_key="key-after-error"
    )

    assert too_many_guests.status_code == 400
    assert fixed.status_code == 201, "a rolled-back request leaves the key free"


async def test_idempotency_key_is_required(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> None:
    response = await client.post(
        "/api/v1/bookings",
        json={
            "listing_id": str(priced_listing.id),
            "check_in": str(next_monday),
            "check_out": str(next_monday + timedelta(3)),
            "guests": 1,
        },
        headers=auth(uuid4()),
    )

    assert response.status_code == 422


async def test_expired_hold_releases_the_dates(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date, db: Database
) -> None:
    first = (await book(client, auth(uuid4()), priced_listing, next_monday)).json()
    async with db.engine.begin() as connection:
        await connection.execute(
            text("UPDATE bookings SET hold_expires_at = now() - interval '1 minute'")
        )

    second = await book(client, auth(uuid4()), priced_listing, next_monday)
    guest_view = await client.get(
        f"/api/v1/bookings/{first['id']}", headers=auth(first["guest_id"])
    )

    assert second.status_code == 201
    assert guest_view.json()["status"] == "expired"


async def test_host_cannot_book_own_listing(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> None:
    response = await book(client, auth(priced_listing.host_id), priced_listing, next_monday)

    assert response.status_code == 400


async def test_host_cannot_block_booked_nights(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> None:
    await book(client, auth(uuid4()), priced_listing, next_monday)

    response = await client.post(
        f"/api/v1/host/listings/{priced_listing.id}/blocks",
        json={
            "start_date": str(next_monday + timedelta(1)),
            "end_date": str(next_monday + timedelta(5)),
        },
        headers=auth(priced_listing.host_id, "host"),
    )

    assert response.status_code == 409


async def test_bookings_are_visible_to_their_guest_and_host_only(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> None:
    guest_id = uuid4()
    booking = (await book(client, auth(guest_id), priced_listing, next_monday)).json()
    host = auth(priced_listing.host_id, "host")

    mine = await client.get("/api/v1/bookings", headers=auth(guest_id))
    stranger = await client.get(f"/api/v1/bookings/{booking['id']}", headers=auth(uuid4()))
    as_host = await client.get(f"/api/v1/host/bookings/{booking['id']}", headers=host)
    host_list = await client.get(
        "/api/v1/host/bookings", params={"listing_id": str(priced_listing.id)}, headers=host
    )

    assert [b["id"] for b in mine.json()["items"]] == [booking["id"]]
    assert stranger.status_code == 404
    assert as_host.status_code == 200
    assert [b["id"] for b in host_list.json()["items"]] == [booking["id"]]
