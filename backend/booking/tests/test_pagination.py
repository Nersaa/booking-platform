from datetime import date, timedelta
from uuid import uuid4

from httpx import AsyncClient

from app.listings.models import Listing
from tests.helpers import Headers, book

WEEK = timedelta(days=7)


async def test_guest_bookings_are_paged_newest_first(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> None:
    guest = auth(uuid4())
    made = [
        (await book(client, guest, priced_listing, next_monday + n * WEEK)).json()["id"]
        for n in range(5)
    ]

    first = (await client.get("/api/v1/bookings", params={"limit": 2}, headers=guest)).json()
    rest = (
        await client.get("/api/v1/bookings", params={"limit": 3, "offset": 2}, headers=guest)
    ).json()

    assert [b["id"] for b in first["items"] + rest["items"]] == made[::-1]
    assert (first["total"], first["limit"], first["offset"]) == (5, 2, 0)


async def test_host_bookings_are_paged_by_check_in(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> None:
    for n in (2, 0, 1):
        await book(client, auth(uuid4()), priced_listing, next_monday + n * WEEK)
    host = auth(priced_listing.host_id, "host")

    first = (await client.get("/api/v1/host/bookings", params={"limit": 2}, headers=host)).json()
    second = (await client.get("/api/v1/host/bookings", params={"offset": 2}, headers=host)).json()

    check_ins = [b["check_in"] for b in first["items"] + second["items"]]
    assert check_ins == sorted(check_ins)
    assert first["total"] == 3
