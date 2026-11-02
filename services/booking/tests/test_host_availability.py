from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.listings.models import Listing

PRICING = {
    "currency": "EUR",
    "nightly_price": 10_000,
    "weekend_price": 14_000,
    "cleaning_fee": 2_500,
    "min_nights": 2,
    "max_nights": 30,
    "weekly_discount_percent": 10,
    "monthly_discount_percent": 20,
}

Headers = Callable[..., dict[str, str]]


@pytest.fixture
async def listing(make_listing: Callable[..., Any]) -> Listing:
    created: Listing = await make_listing()
    return created


@pytest.fixture
def host(auth: Headers, listing: Listing) -> dict[str, str]:
    return auth(listing.host_id, "guest", "host")


def url(listing: Listing, path: str) -> str:
    return f"/api/v1/host/listings/{listing.id}/{path}"


def period(start: date, nights: int) -> dict[str, str]:
    return {"start_date": start.isoformat(), "end_date": (start + timedelta(nights)).isoformat()}


async def test_pricing_is_created_then_replaced(
    client: AsyncClient, listing: Listing, host: dict[str, str]
) -> None:
    missing = await client.get(url(listing, "pricing"), headers=host)
    assert missing.status_code == 404

    created = await client.put(url(listing, "pricing"), json=PRICING, headers=host)
    assert created.status_code == 200, created.text
    assert created.json() | PRICING == created.json()

    updated = await client.put(
        url(listing, "pricing"), json=PRICING | {"nightly_price": 12_000}, headers=host
    )
    assert updated.json()["nightly_price"] == 12_000

    fetched = await client.get(url(listing, "pricing"), headers=host)
    assert fetched.json()["nightly_price"] == 12_000


@pytest.mark.parametrize(
    "invalid",
    [
        {"currency": "eur"},
        {"nightly_price": 0},
        {"min_nights": 5, "max_nights": 3},
        {"weekly_discount_percent": 95},
    ],
)
async def test_invalid_pricing_is_rejected(
    client: AsyncClient, listing: Listing, host: dict[str, str], invalid: dict[str, Any]
) -> None:
    response = await client.put(url(listing, "pricing"), json=PRICING | invalid, headers=host)

    assert response.status_code == 422
    assert response.json()["errors"]


async def test_other_hosts_cannot_see_the_listing(
    client: AsyncClient, listing: Listing, auth: Headers
) -> None:
    stranger = auth(uuid4(), "guest", "host")

    response = await client.put(url(listing, "pricing"), json=PRICING, headers=stranger)

    assert response.status_code == 404


async def test_seasonal_rates_cannot_overlap(
    client: AsyncClient, listing: Listing, host: dict[str, str], next_monday: date
) -> None:
    summer = {**period(next_monday, 14), "nightly_price": 20_000}
    created = await client.post(url(listing, "seasonal-rates"), json=summer, headers=host)
    assert created.status_code == 201, created.text

    overlapping = {**period(next_monday + timedelta(13), 5), "nightly_price": 18_000}
    conflict = await client.post(url(listing, "seasonal-rates"), json=overlapping, headers=host)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "conflict"

    # Periods are half-open, so a season may start on the day the previous one ends.
    adjacent = {**period(next_monday + timedelta(14), 5), "nightly_price": 18_000}
    assert (
        await client.post(url(listing, "seasonal-rates"), json=adjacent, headers=host)
    ).status_code == 201

    rates = (await client.get(url(listing, "seasonal-rates"), headers=host)).json()
    assert [rate["start_date"] for rate in rates] == [summer["start_date"], adjacent["start_date"]]


async def test_seasonal_rate_can_be_deleted(
    client: AsyncClient, listing: Listing, host: dict[str, str], next_monday: date
) -> None:
    body = {**period(next_monday, 3), "nightly_price": 20_000}
    rate = (await client.post(url(listing, "seasonal-rates"), json=body, headers=host)).json()

    deleted = await client.delete(url(listing, f"seasonal-rates/{rate['id']}"), headers=host)
    again = await client.delete(url(listing, f"seasonal-rates/{rate['id']}"), headers=host)

    assert deleted.status_code == 204
    assert again.status_code == 404


async def test_blocks_cannot_overlap_and_can_be_removed(
    client: AsyncClient, listing: Listing, host: dict[str, str], next_monday: date
) -> None:
    block = await client.post(
        url(listing, "blocks"), json={**period(next_monday, 3), "note": "Family"}, headers=host
    )
    assert block.status_code == 201, block.text

    overlap = await client.post(
        url(listing, "blocks"), json=period(next_monday + timedelta(2), 2), headers=host
    )
    assert overlap.status_code == 409

    listed = (await client.get(url(listing, "blocks"), headers=host)).json()
    assert [b["note"] for b in listed] == ["Family"]

    removed = await client.delete(url(listing, f"blocks/{block.json()['id']}"), headers=host)
    assert removed.status_code == 204


async def test_past_dates_cannot_be_blocked(
    client: AsyncClient, listing: Listing, host: dict[str, str]
) -> None:
    yesterday = datetime.now(UTC).date() - timedelta(days=1)

    response = await client.post(url(listing, "blocks"), json=period(yesterday, 2), headers=host)

    assert response.status_code == 400


async def test_period_must_be_forward_and_bounded(
    client: AsyncClient, listing: Listing, host: dict[str, str], next_monday: date
) -> None:
    backwards = {"start_date": next_monday.isoformat(), "end_date": next_monday.isoformat()}
    too_long = period(next_monday, 400)

    for body in (backwards, too_long):
        response = await client.post(url(listing, "blocks"), json=body, headers=host)
        assert response.status_code == 422
