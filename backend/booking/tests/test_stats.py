import itertools
import random
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range

from app.bookings.models import Booking
from app.db import Database
from app.demo_stays import add_past_stays
from app.listings.models import Listing
from tests.helpers import Headers

YEAR = 2025


async def add_booking(
    db: Database,
    listing: Listing,
    check_in: date,
    check_out: date,
    total: int,
    status: str = "confirmed",
    currency: str = "EUR",
) -> None:
    async with db.sessions.begin() as session:
        session.add(
            Booking(
                listing_id=listing.id,
                guest_id=uuid4(),
                host_id=listing.host_id,
                period=Range(check_in, check_out),
                guests=2,
                status=status,
                currency=currency,
                subtotal=total,
                discount=0,
                cleaning_fee=0,
                total=total,
            )
        )


async def stats(client: AsyncClient, auth: Headers, host_id: UUID, **params: Any) -> Any:
    response = await client.get(
        "/api/v1/host/stats", params={"year": YEAR, **params}, headers=auth(host_id, "host")
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_host_stats_by_month(
    client: AsyncClient, make_listing: Callable[..., Any], auth: Headers, db: Database
) -> None:
    host_id = uuid4()
    loft = await make_listing(host_id=host_id, title="Loft")
    cabin = await make_listing(host_id=host_id, title="Cabin")
    someone_elses = await make_listing()

    await add_booking(db, loft, date(YEAR, 6, 28), date(YEAR, 7, 2), 40_000)  # 3 + 1 nights
    await add_booking(db, cabin, date(YEAR, 3, 10), date(YEAR, 3, 12), 10_000, "completed")
    await add_booking(db, cabin, date(YEAR, 8, 1), date(YEAR, 8, 5), 99_000, "cancelled")
    await add_booking(db, cabin, date(YEAR, 9, 1), date(YEAR, 9, 2), 7_000, currency="USD")
    await add_booking(db, someone_elses, date(YEAR, 6, 1), date(YEAR, 6, 9), 50_000)

    data = await stats(client, auth, host_id)

    assert data["currency"] == "EUR"
    assert data["currencies"] == ["EUR", "USD"]
    assert data["listed_places"] == 2
    assert (data["revenue"], data["bookings"], data["average_booking"]) == (50_000, 2, 25_000)
    assert data["nights"] == 7, "nights are counted in every currency"
    months = {m["month"][5:7]: m for m in data["months"]}
    assert len(months) == 12
    assert (months["06"]["revenue"], months["06"]["nights"]) == (40_000, 3)
    assert (months["07"]["revenue"], months["07"]["nights"]) == (0, 1)
    assert months["06"]["occupancy_percent"] == 5.0  # 3 nights of 2 places x 30 days
    assert months["08"]["nights"] == 0, "cancelled stays do not count"
    assert [t["title"] for t in data["top_listings"]] == ["Loft", "Cabin"]


async def test_host_stats_in_another_currency(
    client: AsyncClient, make_listing: Callable[..., Any], auth: Headers, db: Database
) -> None:
    listing = await make_listing()
    await add_booking(db, listing, date(YEAR, 9, 1), date(YEAR, 9, 3), 7_000, currency="USD")

    data = await stats(client, auth, listing.host_id, currency="USD")

    assert (data["currency"], data["revenue"]) == ("USD", 7_000)


async def test_stats_are_for_hosts_only(client: AsyncClient, auth: Headers) -> None:
    response = await client.get("/api/v1/host/stats", headers=auth(uuid4()))

    assert response.status_code == 403


async def test_demo_stays_fill_a_year_once(
    client: AsyncClient, priced_listing: Listing, db: Database
) -> None:
    async with db.sessions.begin() as session:
        added = await add_past_stays(session, random.Random(1))
    async with db.sessions.begin() as session:
        again = await add_past_stays(session, random.Random(1))
        stays = (await session.scalars(select(Booking).order_by(Booking.period))).all()

    assert added == len(stays) > 20
    assert again == 0, "listings with a history are skipped"
    today = datetime.now(UTC).date()
    for before, after in itertools.pairwise(stays):
        assert before.check_out <= after.check_in, "stays never overlap"
    assert stays[-1].check_out <= today
    assert all(s.total == s.subtotal + s.cleaning_fee for s in stays)


async def test_host_can_list_only_upcoming_stays(
    client: AsyncClient, make_listing: Callable[..., Any], auth: Headers, db: Database
) -> None:
    listing = await make_listing()
    today = datetime.now(UTC).date()
    await add_booking(db, listing, date(2025, 3, 1), date(2025, 3, 4), 9_000, "completed")
    await add_booking(db, listing, today, date(today.year + 1, 1, 9), 9_000)

    response = await client.get(
        "/api/v1/host/bookings",
        params={"upcoming": "true"},
        headers=auth(listing.host_id, "host"),
    )

    assert [b["check_in"] for b in response.json()["items"]] == [str(today)]
