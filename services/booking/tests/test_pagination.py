from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.listings.models import Listing
from app.pagination import CursorValue, InvalidCursorError, decode_cursor, encode_cursor
from tests.helpers import Headers, book

WEEK = timedelta(days=7)


def test_cursor_round_trips_every_key_type() -> None:
    values: list[CursorValue] = [
        12.5,
        7,
        Decimal("4.50"),
        uuid4(),
        date(2030, 1, 2),
        datetime.now(UTC),
    ]
    types: list[type[CursorValue]] = [float, int, Decimal, UUID, date, datetime]

    cursor = encode_cursor("kind", values)

    assert decode_cursor(cursor, "kind", types) == values
    assert "=" not in cursor


@pytest.mark.parametrize(
    "cursor",
    [
        encode_cursor("other-kind", [1]),
        encode_cursor("kind", [1, 2]),
        encode_cursor("kind", ["one"]),  # type: ignore[list-item]
        "%%%",
        "",
    ],
)
def test_foreign_or_broken_cursors_are_rejected(cursor: str) -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor(cursor or "e30", "kind", [int])


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
        await client.get(
            "/api/v1/bookings", params={"limit": 3, "cursor": first["next_cursor"]}, headers=guest
        )
    ).json()

    assert [b["id"] for b in first["items"] + rest["items"]] == made[::-1]
    assert rest["next_cursor"] is None


async def test_host_bookings_are_paged_by_check_in(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> None:
    for n in (2, 0, 1):
        await book(client, auth(uuid4()), priced_listing, next_monday + n * WEEK)
    host = auth(priced_listing.host_id, "host")

    first = (await client.get("/api/v1/host/bookings", params={"limit": 2}, headers=host)).json()
    second = (
        await client.get(
            "/api/v1/host/bookings", params={"cursor": first["next_cursor"]}, headers=host
        )
    ).json()

    check_ins = [b["check_in"] for b in first["items"] + second["items"]]
    assert check_ins == sorted(check_ins)
    assert len(check_ins) == 3
