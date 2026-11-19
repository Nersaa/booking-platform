"""Pricing and availability use cases. Routers only translate HTTP to these calls."""

from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, Delete, delete, func, select
from sqlalchemy.dialects.postgresql import Range, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal
from app.availability.models import (
    AvailabilityBlock,
    ListingPricing,
    SeasonalRate,
    period_bounds,
)
from app.availability.pricing import (
    PriceRules,
    Season,
    StayPrice,
    night_price,
    nights_between,
    price_stay,
)
from app.availability.schemas import (
    BlockIn,
    CalendarDay,
    CalendarOut,
    PricingIn,
    QuoteNight,
    QuoteOut,
    SeasonalRateIn,
)
from app.bookings.models import Booking
from app.errors import ConflictError, DomainError, NotFoundError
from app.listings.models import Listing

EXCLUSION_VIOLATION = "23P01"
MAX_CALENDAR_DAYS = 366
BOOKING_WINDOW_DAYS = 730


class InvalidStayError(DomainError):
    code = "invalid_stay"


class DatesUnavailableError(ConflictError):
    code = "dates_unavailable"


def today() -> date:
    return datetime.now(UTC).date()


# Host side


async def get_host_listing(session: AsyncSession, listing_id: UUID, host: Principal) -> Listing:
    listing = await session.get(Listing, listing_id)
    # Someone else's listing looks exactly like a missing one.
    if listing is None or listing.host_id != host.user_id:
        raise NotFoundError(
            "Listing not found. A newly published listing appears here within a few seconds."
        )
    return listing


async def get_pricing(session: AsyncSession, listing: Listing) -> ListingPricing:
    pricing = await session.get(ListingPricing, listing.id)
    if pricing is None:
        raise NotFoundError("Pricing is not configured for this listing yet.")
    return pricing


async def set_pricing(session: AsyncSession, listing: Listing, data: PricingIn) -> ListingPricing:
    values = data.model_dump()
    stmt = (
        insert(ListingPricing)
        .values(listing_id=listing.id, **values)
        .on_conflict_do_update(
            index_elements=[ListingPricing.listing_id], set_={**values, "updated_at": func.now()}
        )
        .returning(ListingPricing)
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(stmt)).one()


async def list_seasonal_rates(session: AsyncSession, listing: Listing) -> Sequence[SeasonalRate]:
    stmt = (
        select(SeasonalRate)
        .where(SeasonalRate.listing_id == listing.id)
        .order_by(func.lower(SeasonalRate.period))
    )
    return (await session.scalars(stmt)).all()


async def add_seasonal_rate(
    session: AsyncSession, listing: Listing, data: SeasonalRateIn
) -> SeasonalRate:
    rate = SeasonalRate(
        listing_id=listing.id,
        period=Range(data.start_date, data.end_date),
        nightly_price=data.nightly_price,
    )
    await _insert(session, rate, "The period overlaps another seasonal rate.")
    return rate


async def delete_seasonal_rate(session: AsyncSession, listing: Listing, rate_id: UUID) -> None:
    stmt = delete(SeasonalRate).where(
        SeasonalRate.id == rate_id, SeasonalRate.listing_id == listing.id
    )
    if not await _deleted(session, stmt):
        raise NotFoundError("Seasonal rate not found.")


async def list_blocks(session: AsyncSession, listing: Listing) -> Sequence[AvailabilityBlock]:
    stmt = (
        select(AvailabilityBlock)
        .where(
            AvailabilityBlock.listing_id == listing.id,
            func.upper(AvailabilityBlock.period) > today(),
        )
        .order_by(func.lower(AvailabilityBlock.period))
    )
    return (await session.scalars(stmt)).all()


async def add_block(session: AsyncSession, listing: Listing, data: BlockIn) -> AvailabilityBlock:
    if data.start_date < today():
        raise DomainError("Past dates cannot be blocked.")
    # Same lock as booking creation: a block and a booking cannot slip in side by side.
    await lock_listing(session, listing.id)
    if await _booked_nights(session, listing.id, data.start_date, data.end_date):
        raise DatesUnavailableError("Some of these nights are already booked.")
    block = AvailabilityBlock(
        listing_id=listing.id, period=Range(data.start_date, data.end_date), note=data.note
    )
    await _insert(session, block, "The period overlaps dates that are already blocked.")
    return block


async def delete_block(session: AsyncSession, listing: Listing, block_id: UUID) -> None:
    stmt = delete(AvailabilityBlock).where(
        AvailabilityBlock.id == block_id, AvailabilityBlock.listing_id == listing.id
    )
    if not await _deleted(session, stmt):
        raise NotFoundError("Block not found.")


# Guest side


async def get_calendar(
    session: AsyncSession, listing_id: UUID, start: date, end: date
) -> CalendarOut:
    if start < today():
        raise DomainError("The calendar cannot start in the past.")
    if end <= start or (end - start).days > MAX_CALENDAR_DAYS:
        raise DomainError(f"end_date must be 1 to {MAX_CALENDAR_DAYS} days after start_date.")

    _, pricing = await _bookable(session, listing_id)
    rules = price_rules(pricing)
    seasons = await _seasons(session, listing_id, start, end)
    blocked = await _unavailable_nights(session, listing_id, start, end)
    return CalendarOut(
        listing_id=listing_id,
        currency=pricing.currency,
        min_nights=pricing.min_nights,
        max_nights=pricing.max_nights,
        instant_book=pricing.instant_book,
        days=[
            CalendarDay(
                date=night,
                available=night not in blocked,
                nightly_price=night_price(rules, seasons, night),
            )
            for night in nights_between(start, end)
        ],
    )


async def price_available_stay(
    session: AsyncSession,
    listing_id: UUID,
    check_in: date,
    check_out: date,
    guests: int,
    *,
    lock: bool = False,
) -> tuple[Listing, ListingPricing, StayPrice]:
    """Validate a stay against the listing's rules and calendar, then price it.

    With `lock=True` the listing row stays locked until the transaction ends, so the
    caller can book the dates without anyone taking them in between.
    """
    if check_in < today():
        raise InvalidStayError("Check-in cannot be in the past.")
    if check_out <= check_in:
        raise InvalidStayError("Check-out must be after check-in.")
    if check_in > today() + timedelta(days=BOOKING_WINDOW_DAYS):
        raise InvalidStayError(f"Bookings open {BOOKING_WINDOW_DAYS} days in advance.")

    listing, pricing = await _bookable(session, listing_id, lock=lock)
    nights = (check_out - check_in).days
    if not pricing.min_nights <= nights <= pricing.max_nights:
        raise InvalidStayError(
            f"Stays must be {pricing.min_nights} to {pricing.max_nights} nights long."
        )
    if guests > listing.max_guests:
        raise InvalidStayError(f"This place hosts at most {listing.max_guests} guests.")
    if await _unavailable_nights(session, listing_id, check_in, check_out):
        raise DatesUnavailableError("Some of the selected nights are not available.")

    seasons = await _seasons(session, listing_id, check_in, check_out)
    return listing, pricing, price_stay(price_rules(pricing), seasons, check_in, check_out)


async def get_quote(
    session: AsyncSession, listing_id: UUID, check_in: date, check_out: date, guests: int
) -> QuoteOut:
    _, pricing, stay = await price_available_stay(session, listing_id, check_in, check_out, guests)
    return QuoteOut(
        listing_id=listing_id,
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        currency=pricing.currency,
        nights=[QuoteNight(date=n.night, price=n.price) for n in stay.nights],
        subtotal=stay.subtotal,
        discount=stay.discount,
        discount_type=stay.discount_type,
        cleaning_fee=stay.cleaning_fee,
        total=stay.total,
    )


# Helpers


async def _insert(session: AsyncSession, obj: object, conflict_message: str) -> None:
    session.add(obj)
    try:
        await session.flush()
    except IntegrityError as exc:
        # The exclusion constraint is the source of truth, even under concurrent requests.
        if getattr(exc.orig, "sqlstate", None) == EXCLUSION_VIOLATION:
            raise ConflictError(conflict_message) from exc
        raise


async def _deleted(session: AsyncSession, stmt: Delete) -> bool:
    result = cast(CursorResult[Any], await session.execute(stmt))
    return result.rowcount > 0


async def lock_listing(session: AsyncSession, listing_id: UUID) -> None:
    """Serialises changes to one listing's calendar (bookings and blocks)."""
    await session.execute(select(Listing.id).where(Listing.id == listing_id).with_for_update())


async def _bookable(
    session: AsyncSession, listing_id: UUID, *, lock: bool = False
) -> tuple[Listing, ListingPricing]:
    """A listing can be booked once it is published and the host has set a price."""
    stmt = (
        select(Listing, ListingPricing)
        .join(ListingPricing, ListingPricing.listing_id == Listing.id)
        .where(Listing.id == listing_id, Listing.is_listed)
    )
    if lock:
        stmt = stmt.with_for_update(of=Listing)
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        raise NotFoundError("This listing is not available for booking.")
    listing, pricing = row
    return listing, pricing


def price_rules(pricing: ListingPricing) -> PriceRules:
    return PriceRules(
        nightly_price=pricing.nightly_price,
        weekend_price=pricing.weekend_price,
        cleaning_fee=pricing.cleaning_fee,
        weekly_discount_percent=pricing.weekly_discount_percent,
        monthly_discount_percent=pricing.monthly_discount_percent,
    )


async def _seasons(session: AsyncSession, listing_id: UUID, start: date, end: date) -> list[Season]:
    stmt = select(SeasonalRate).where(
        SeasonalRate.listing_id == listing_id,
        SeasonalRate.period.overlaps(Range(start, end)),
    )
    return [
        Season(*period_bounds(rate.period), nightly_price=rate.nightly_price)
        for rate in await session.scalars(stmt)
    ]


async def _unavailable_nights(
    session: AsyncSession, listing_id: UUID, start: date, end: date
) -> set[date]:
    """Nights closed by the host or held by an active booking."""
    blocks = select(AvailabilityBlock.period).where(
        AvailabilityBlock.listing_id == listing_id,
        AvailabilityBlock.period.overlaps(Range(start, end)),
    )
    nights = _expand(await session.scalars(blocks), start, end)
    return nights | await _booked_nights(session, listing_id, start, end)


async def _booked_nights(
    session: AsyncSession, listing_id: UUID, start: date, end: date
) -> set[date]:
    stmt = select(Booking.period).where(
        Booking.listing_id == listing_id,
        Booking.period.overlaps(Range(start, end)),
        Booking.holds_dates(),
    )
    return _expand(await session.scalars(stmt), start, end)


def _expand(periods: Iterable[Range[date]], start: date, end: date) -> set[date]:
    nights: set[date] = set()
    for period in periods:
        lower, upper = period_bounds(period)
        nights.update(nights_between(max(lower, start), min(upper, end)))
    return nights
