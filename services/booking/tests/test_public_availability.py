from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.listings.models import Listing
from tests.test_host_availability import period

Headers = Callable[..., dict[str, str]]


async def _host_post(
    client: AsyncClient, auth: Headers, listing: Listing, path: str, body: dict[str, Any]
) -> None:
    response = await client.post(
        f"/api/v1/host/listings/{listing.id}/{path}",
        json=body,
        headers=auth(listing.host_id, "host"),
    )
    assert response.status_code == 201, response.text


def quote_url(listing: Listing, check_in: date, nights: int, guests: int = 2) -> str:
    check_out = check_in + timedelta(days=nights)
    return (
        f"/api/v1/listings/{listing.id}/quote"
        f"?check_in={check_in}&check_out={check_out}&guests={guests}"
    )


async def test_calendar_shows_prices_and_blocked_nights(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> None:
    await _host_post(client, auth, priced_listing, "blocks", period(next_monday + timedelta(1), 2))
    await _host_post(
        client,
        auth,
        priced_listing,
        "seasonal-rates",
        {**period(next_monday + timedelta(5), 1), "nightly_price": 30_000},
    )

    response = await client.get(
        f"/api/v1/listings/{priced_listing.id}/calendar",
        params={"start_date": str(next_monday), "end_date": str(next_monday + timedelta(7))},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["currency"], body["min_nights"], body["max_nights"]) == ("EUR", 2, 30)
    days = body["days"]
    assert [d["available"] for d in days] == [True, False, False, True, True, True, True]
    # Mon..Thu regular, Fri weekend, Sat seasonal (wins over weekend), Sun regular.
    assert [d["nightly_price"] for d in days] == [10_000] * 4 + [14_000, 30_000, 10_000]


async def test_calendar_defaults_to_ninety_nights(
    client: AsyncClient, priced_listing: Listing
) -> None:
    response = await client.get(f"/api/v1/listings/{priced_listing.id}/calendar")

    days = response.json()["days"]
    assert len(days) == 90
    assert days[0]["date"] == datetime.now(UTC).date().isoformat()


async def test_calendar_range_is_validated(client: AsyncClient, priced_listing: Listing) -> None:
    today = datetime.now(UTC).date()
    calendar = f"/api/v1/listings/{priced_listing.id}/calendar"

    past = await client.get(calendar, params={"start_date": str(today - timedelta(days=1))})
    too_long = await client.get(
        calendar, params={"start_date": str(today), "end_date": str(today + timedelta(days=400))}
    )

    assert past.status_code == 400
    assert too_long.status_code == 400


async def test_listing_without_pricing_or_archived_is_not_bookable(
    client: AsyncClient, make_listing: Callable[..., Any], priced_listing: Listing
) -> None:
    unpriced: Listing = await make_listing()
    await make_listing(id=priced_listing.id, version=priced_listing.version + 1, is_listed=False)

    for listing_id in (unpriced.id, priced_listing.id, uuid4()):
        response = await client.get(f"/api/v1/listings/{listing_id}/calendar")
        assert response.status_code == 404


async def test_quote_breaks_down_the_price(
    client: AsyncClient, priced_listing: Listing, next_monday: date
) -> None:
    response = await client.get(quote_url(priced_listing, next_monday, nights=7))

    assert response.status_code == 200, response.text
    quote = response.json()
    assert len(quote["nights"]) == 7
    assert quote["subtotal"] == 5 * 10_000 + 2 * 14_000
    assert quote["discount_type"] == "weekly"
    assert quote["discount"] == 7_800
    assert quote["cleaning_fee"] == 2_500
    assert quote["total"] == 78_000 - 7_800 + 2_500
    assert quote["currency"] == "EUR"


async def test_quote_rejects_blocked_dates(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> None:
    await _host_post(client, auth, priced_listing, "blocks", period(next_monday + timedelta(2), 1))

    response = await client.get(quote_url(priced_listing, next_monday, nights=3))

    assert response.status_code == 409
    assert response.json()["code"] == "dates_unavailable"


async def test_check_out_day_may_be_blocked(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> None:
    await _host_post(client, auth, priced_listing, "blocks", period(next_monday + timedelta(3), 2))

    response = await client.get(quote_url(priced_listing, next_monday, nights=3))

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("offset", "nights", "guests"),
    [
        (-1, 3, 2),  # check-in in the past
        (0, 1, 2),  # shorter than min_nights
        (0, 31, 2),  # longer than max_nights
        (0, 3, 4),  # more guests than the place hosts
        (800, 3, 2),  # beyond the booking window
    ],
)
async def test_quote_rejects_invalid_stays(
    client: AsyncClient, priced_listing: Listing, offset: int, nights: int, guests: int
) -> None:
    check_in = datetime.now(UTC).date() + timedelta(days=offset)

    response = await client.get(quote_url(priced_listing, check_in, nights, guests))

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_stay"


async def test_quote_requires_check_out_after_check_in(
    client: AsyncClient, priced_listing: Listing, next_monday: date
) -> None:
    response = await client.get(
        f"/api/v1/listings/{priced_listing.id}/quote?check_in={next_monday}&check_out={next_monday}"
    )

    assert response.status_code == 400
