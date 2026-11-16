"""Listing search: geo, filters and availability in one SQL query, paginated by keyset.

Geo filters use the GiST index on the generated `location` column; amenities use the GIN
index; availability is two NOT EXISTS probes into the same GiST indexes that enforce
"no overlapping bookings" and "no overlapping blocks".
"""

from collections import defaultdict
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, exists, func, literal, select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.availability.models import AvailabilityBlock, ListingPricing, SeasonalRate, period_bounds
from app.availability.pricing import Season, price_stay
from app.availability.service import InvalidStayError, price_rules, today
from app.bookings.models import Booking
from app.listings.models import Listing
from app.pagination import Page, count
from app.search.schemas import SearchParams, SearchResult, Sort

WGS84 = 4326


async def search(session: AsyncSession, params: SearchParams) -> Page[SearchResult]:
    if params.check_in and params.check_in < today():
        raise InvalidStayError("Check-in cannot be in the past.")

    point = _point(params.lon, params.lat) if params.lat is not None else None
    distance = func.ST_Distance(Listing.location, point) if point is not None else literal(None)
    stmt = _filtered(
        select(Listing, ListingPricing, distance.label("distance"))
        .join(ListingPricing, ListingPricing.listing_id == Listing.id)
        .where(Listing.is_listed),
        params,
        point,
    )

    total = await count(session, stmt)
    page_stmt = stmt.order_by(*_order(params.effective_sort, distance))
    page = (await session.execute(page_stmt.limit(params.limit).offset(params.offset))).all()

    totals = await _stay_totals(
        session, params, [(listing, pricing) for listing, pricing, _ in page]
    )
    items = [
        _result(listing, pricing, meters, totals.get(listing.id))
        for listing, pricing, meters in page
    ]
    return Page(items=items, total=total, limit=params.limit, offset=params.offset)


def _point(lon: float | None, lat: float | None) -> ColumnElement[Any]:
    return func.geography(func.ST_SetSRID(func.ST_MakePoint(lon, lat), WGS84))


def _filtered(
    stmt: Select[Any], params: SearchParams, point: ColumnElement[Any] | None
) -> Select[Any]:
    if point is not None:
        stmt = stmt.where(func.ST_DWithin(Listing.location, point, params.radius_km * 1000))
    if bounds := params.bounds:
        envelope = func.geography(func.ST_MakeEnvelope(*bounds, WGS84))
        stmt = stmt.where(func.ST_Intersects(Listing.location, envelope))
    if params.country:
        stmt = stmt.where(Listing.country == params.country)
    if params.city:
        stmt = stmt.where(func.lower(Listing.city) == params.city.lower())
    if params.property_type:
        stmt = stmt.where(Listing.property_type.in_(params.property_type))
    if params.amenities:
        stmt = stmt.where(Listing.amenities.contains(params.amenities))
    if params.min_bedrooms is not None:
        stmt = stmt.where(Listing.bedrooms >= params.min_bedrooms)
    if params.min_rating is not None:
        stmt = stmt.where(Listing.rating >= params.min_rating)
    if params.currency:
        stmt = stmt.where(ListingPricing.currency == params.currency)
    if params.min_price is not None:
        stmt = stmt.where(ListingPricing.nightly_price >= params.min_price)
    if params.max_price is not None:
        stmt = stmt.where(ListingPricing.nightly_price <= params.max_price)
    stmt = stmt.where(Listing.max_guests >= params.guests)
    if params.check_in and params.check_out:
        stmt = _available(stmt, params.check_in, params.check_out)
    return stmt


def _available(stmt: Select[Any], check_in: date, check_out: date) -> Select[Any]:
    stay = Range(check_in, check_out)
    nights = (check_out - check_in).days
    blocked = exists().where(
        AvailabilityBlock.listing_id == Listing.id, AvailabilityBlock.period.overlaps(stay)
    )
    booked = exists().where(
        Booking.listing_id == Listing.id, Booking.period.overlaps(stay), Booking.holds_dates()
    )
    return stmt.where(
        ListingPricing.min_nights <= nights,
        ListingPricing.max_nights >= nights,
        ~blocked,
        ~booked,
    )


def _order(sort: Sort, distance: ColumnElement[Any]) -> list[ColumnElement[Any]]:
    # The id breaks ties, so the order is stable from page to page.
    if sort == "distance":
        return [distance.asc(), Listing.id.asc()]
    if sort == "price":
        return [ListingPricing.nightly_price.asc(), Listing.id.asc()]
    return [
        func.coalesce(Listing.rating, 0).desc(),
        Listing.review_count.desc(),
        Listing.id.asc(),
    ]


async def _stay_totals(
    session: AsyncSession, params: SearchParams, rows: list[tuple[Listing, ListingPricing]]
) -> dict[UUID, int]:
    """Prices the searched stay for one page of results, with one query for the seasons."""
    if not (params.check_in and params.check_out and rows):
        return {}
    check_in, check_out = params.check_in, params.check_out
    stmt = select(SeasonalRate).where(
        SeasonalRate.listing_id.in_([listing.id for listing, _ in rows]),
        SeasonalRate.period.overlaps(Range(check_in, check_out)),
    )
    seasons: dict[UUID, list[Season]] = defaultdict(list)
    for rate in await session.scalars(stmt):
        start, end = period_bounds(rate.period)
        seasons[rate.listing_id].append(Season(start, end, nightly_price=rate.nightly_price))
    return {
        listing.id: price_stay(price_rules(pricing), seasons[listing.id], check_in, check_out).total
        for listing, pricing in rows
    }


def _result(
    listing: Listing, pricing: ListingPricing, meters: float | None, stay_total: int | None
) -> SearchResult:
    return SearchResult(
        id=listing.id,
        title=listing.title,
        property_type=listing.property_type,
        country=listing.country,
        city=listing.city,
        latitude=listing.latitude,
        longitude=listing.longitude,
        max_guests=listing.max_guests,
        bedrooms=listing.bedrooms,
        beds=listing.beds,
        bathrooms=listing.bathrooms,
        amenities=listing.amenities,
        cover_photo_url=listing.cover_photo_url,
        rating=listing.rating,
        review_count=listing.review_count,
        currency=pricing.currency,
        nightly_price=pricing.nightly_price,
        distance_km=round(meters / 1000, 2) if meters is not None else None,
        stay_total=stay_total,
    )
