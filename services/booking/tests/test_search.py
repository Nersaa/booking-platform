from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.bookings.models import Booking
from app.db import Database
from app.listings.models import Listing
from app.settings import Settings
from tests.factories import PRICING
from tests.helpers import Headers, book

URL = "/api/v1/listings"
LISBON = {"lat": 38.7223, "lon": -9.1393}
LISBON_BBOX = "-9.25,38.68,-9.08,38.80"

MakeListing = Callable[..., Any]


@pytest.fixture
def add(client: AsyncClient, make_listing: MakeListing, auth: Headers) -> Callable[..., Any]:
    """A bookable listing: in the read model and priced by its host."""

    async def add(pricing: dict[str, Any] | None = None, **fields: Any) -> Listing:
        listing: Listing = await make_listing(**fields)
        response = await client.put(
            f"/api/v1/host/listings/{listing.id}/pricing",
            json={**PRICING, **(pricing or {})},
            headers=auth(listing.host_id, "host"),
        )
        assert response.status_code == 200
        return listing

    return add


async def ids(client: AsyncClient, **params: Any) -> list[str]:
    response = await client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


async def test_map_viewport_returns_bookable_listings_inside_it(
    client: AsyncClient, add: Callable[..., Any], make_listing: MakeListing
) -> None:
    lisbon = await add(latitude=Decimal("38.7100"), longitude=Decimal("-9.1400"))
    await add(city="Porto", latitude=Decimal("41.1579"), longitude=Decimal("-8.6291"))
    await make_listing()  # in the viewport, but no price yet
    await add(is_listed=False)  # archived

    response = await client.get(URL, params={"bbox": LISBON_BBOX})

    [item] = response.json()["items"]
    assert item["id"] == str(lisbon.id)
    assert item["nightly_price"] == PRICING["nightly_price"]
    assert item["currency"] == "EUR"
    assert item["distance_km"] is None
    assert response.json()["next_cursor"] is None


async def test_search_around_a_point_is_sorted_by_distance(
    client: AsyncClient, add: Callable[..., Any]
) -> None:
    sintra = await add(latitude=Decimal("38.8029"), longitude=Decimal("-9.3817"))
    center = await add(latitude=Decimal("38.7139"), longitude=Decimal("-9.1394"))
    await add(latitude=Decimal("41.1579"), longitude=Decimal("-8.6291"))  # Porto, 270 km

    response = await client.get(URL, params={**LISBON, "radius_km": 30})

    items = response.json()["items"]
    assert [item["id"] for item in items] == [str(center.id), str(sintra.id)]
    assert items[0]["distance_km"] == pytest.approx(0.9, abs=0.1)
    assert items[1]["distance_km"] == pytest.approx(22.7, abs=0.5)


async def test_filters_narrow_the_results(client: AsyncClient, add: Callable[..., Any]) -> None:
    house = await add(
        property_type="house",
        bedrooms=3,
        max_guests=6,
        amenities=("kitchen", "pool", "wifi"),
        rating=Decimal("4.70"),
        review_count=10,
    )
    await add(property_type="apartment", bedrooms=1, max_guests=2, amenities=("wifi",))
    await add(property_type="house", pricing={"currency": "USD"}, amenities=("pool",))

    assert await ids(client, guests=5) == [str(house.id)]
    assert await ids(client, min_bedrooms=3, currency="EUR") == [str(house.id)]
    assert await ids(client, amenities=["pool", "wifi"]) == [str(house.id)]
    assert await ids(client, min_rating="4.5") == [str(house.id)]
    assert len(await ids(client, property_type=["house", "cottage"])) == 2
    assert len(await ids(client, country="pt", city="LISBON")) == 3
    assert await ids(client, country="ES") == []


async def test_price_range_applies_to_the_base_nightly_price(
    client: AsyncClient, add: Callable[..., Any]
) -> None:
    cheap = await add(pricing={"nightly_price": 6_000, "weekend_price": None})
    await add(pricing={"nightly_price": 25_000, "weekend_price": None})

    found = await ids(client, currency="EUR", min_price=5_000, max_price=10_000)

    assert found == [str(cheap.id)]


async def test_dates_exclude_booked_and_blocked_listings_and_price_the_stay(
    client: AsyncClient, add: Callable[..., Any], auth: Headers, next_monday: date, db: Database
) -> None:
    free = await add()
    booked = await add()
    blocked = await add()
    stale_hold = await add()
    too_short = await add(pricing={"min_nights": 5})
    await book(client, auth(uuid4()), booked, next_monday)
    await client.post(
        f"/api/v1/host/listings/{blocked.id}/blocks",
        json={
            "start_date": str(next_monday + timedelta(days=2)),
            "end_date": str(next_monday + timedelta(days=9)),
        },
        headers=auth(blocked.host_id, "host"),
    )
    await book(client, auth(uuid4()), stale_hold, next_monday)
    async with db.sessions.begin() as session:
        await session.execute(
            update(Booking)
            .where(Booking.listing_id == stale_hold.id)
            .values(hold_expires_at=Booking.created_at - timedelta(minutes=1))
        )

    check_out = next_monday + timedelta(days=3)
    response = await client.get(
        URL, params={"check_in": str(next_monday), "check_out": str(check_out), "guests": 2}
    )

    found = {item["id"]: item for item in response.json()["items"]}
    assert set(found) == {str(free.id), str(stale_hold.id)}
    assert str(too_short.id) not in found
    quote = await client.get(
        f"/api/v1/listings/{free.id}/quote",
        params={"check_in": str(next_monday), "check_out": str(check_out)},
    )
    assert found[str(free.id)]["stay_total"] == quote.json()["total"]


async def test_default_sort_is_best_rated_first(
    client: AsyncClient, add: Callable[..., Any]
) -> None:
    unrated = await add()
    good = await add(rating=Decimal("4.50"), review_count=40)
    best = await add(rating=Decimal("4.90"), review_count=3)
    popular = await add(rating=Decimal("4.50"), review_count=90)

    assert await ids(client) == [str(item.id) for item in (best, popular, good, unrated)]


async def test_sort_by_price_needs_a_currency(client: AsyncClient, add: Callable[..., Any]) -> None:
    pricey = await add(pricing={"nightly_price": 30_000, "weekend_price": None})
    cheap = await add(pricing={"nightly_price": 5_000, "weekend_price": None})

    assert await ids(client, sort="price", currency="EUR") == [str(cheap.id), str(pricey.id)]
    assert (await client.get(URL, params={"sort": "price"})).status_code == 422


@pytest.mark.parametrize(
    ("sort", "extra"),
    [("rating", {}), ("price", {"currency": "EUR"}), ("distance", LISBON)],
)
async def test_pages_follow_each_other_without_gaps_or_repeats(
    client: AsyncClient, add: Callable[..., Any], sort: str, extra: dict[str, Any]
) -> None:
    # Equal sort values on purpose: the id must break ties for the cursor to be exact.
    created = [
        await add(
            rating=Decimal("4.50"),
            pricing={"nightly_price": 10_000 + 1_000 * (n // 2), "weekend_price": None},
            latitude=Decimal("38.7100") + Decimal("0.0100") * (n // 2),
        )
        for n in range(7)
    ]

    seen: list[str] = []
    params: dict[str, Any] = {"sort": sort, "limit": 3, **extra}
    pages = 0
    while True:
        body = (await client.get(URL, params=params)).json()
        seen += [item["id"] for item in body["items"]]
        pages += 1
        if body["next_cursor"] is None:
            break
        params["cursor"] = body["next_cursor"]

    assert pages == 3
    assert sorted(seen) == sorted(str(listing.id) for listing in created)
    assert len(seen) == len(set(seen))


async def test_a_cursor_works_only_for_its_own_sort(
    client: AsyncClient, add: Callable[..., Any]
) -> None:
    for _ in range(3):
        await add()
    cursor = (await client.get(URL, params={"limit": 1})).json()["next_cursor"]

    other_sort = await client.get(
        URL, params={"cursor": cursor, "sort": "price", "currency": "EUR"}
    )
    garbage = await client.get(URL, params={"cursor": "not-a-cursor"})

    assert other_sort.status_code == 400
    assert other_sort.json()["code"] == "invalid_cursor"
    assert garbage.status_code == 400


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 38.7},
        {"bbox": "-9.2,38.7"},
        {"bbox": "-9.0,38.8,-9.2,38.7"},
        {"bbox": LISBON_BBOX, **LISBON},
        {"min_price": 100},
        {"currency": "EUR", "min_price": 500, "max_price": 100},
        {"sort": "distance"},
        {"check_in": "2030-01-01"},
        {"check_in": "2030-01-05", "check_out": "2030-01-05"},
        {"radius_km": 500, **LISBON},
    ],
)
async def test_invalid_combinations_are_rejected(
    client: AsyncClient, params: dict[str, Any]
) -> None:
    response = await client.get(URL, params=params)

    assert response.status_code == 422


async def test_check_in_cannot_be_in_the_past(client: AsyncClient) -> None:
    past = datetime.now(UTC).date() - timedelta(days=2)

    response = await client.get(
        URL, params={"check_in": str(past), "check_out": str(past + timedelta(days=3))}
    )

    assert response.status_code == 400


class TestCache:
    @pytest.fixture
    def settings(self, settings: Settings) -> Settings:
        return settings.model_copy(update={"search_cache_seconds": 30})

    async def test_repeated_search_is_served_from_cache(
        self, client: AsyncClient, add: Callable[..., Any]
    ) -> None:
        first = await add()
        miss = await client.get(URL, params={"bbox": LISBON_BBOX})
        await add()  # appears only once the cached page expires

        hit = await client.get(URL, params={"bbox": LISBON_BBOX})
        other_query = await client.get(URL, params={"bbox": LISBON_BBOX, "guests": 2})

        assert miss.headers["X-Cache"] == "MISS"
        assert miss.headers["Cache-Control"] == "public, max-age=30"
        assert hit.headers["X-Cache"] == "HIT"
        assert [item["id"] for item in hit.json()["items"]] == [str(first.id)]
        assert len(other_query.json()["items"]) == 2

    async def test_order_of_list_filters_does_not_split_the_cache(
        self, client: AsyncClient
    ) -> None:
        await client.get(URL, params={"amenities": ["wifi", "pool"]})

        response = await client.get(URL, params={"amenities": ["pool", "wifi"]})

        assert response.headers["X-Cache"] == "HIT"
