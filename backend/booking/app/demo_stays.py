"""Past stays for the demo, so the host's statistics have something to show.

    docker compose exec booking-api python -m app.demo_stays

Development only. It writes completed bookings of the last year straight to the
database: no payments, no events, no emails. Listings that already have a completed
stay are skipped, so running it again adds nothing.
"""

import argparse
import asyncio
import random
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.availability.models import ListingPricing
from app.bookings.models import Booking, BookingStatus
from app.db import Database
from app.listings.models import Listing
from app.settings import get_settings


def past_stays(listing: Listing, pricing: ListingPricing, rng: random.Random) -> list[Booking]:
    """Stays one after another over the last year, with a few free nights in between."""
    today = datetime.now(UTC).date()
    stays: list[Booking] = []
    check_in = today - timedelta(days=365 - rng.randint(0, 20))
    while True:
        nights = rng.randint(pricing.min_nights, max(pricing.min_nights, 6))
        check_out = check_in + timedelta(days=nights)
        if check_out > today:
            return stays
        subtotal = nights * pricing.nightly_price
        stays.append(
            Booking(
                listing_id=listing.id,
                guest_id=uuid4(),
                host_id=listing.host_id,
                period=Range(check_in, check_out),
                guests=rng.randint(1, listing.max_guests),
                status=BookingStatus.COMPLETED,
                currency=pricing.currency,
                subtotal=subtotal,
                discount=0,
                cleaning_fee=pricing.cleaning_fee,
                total=subtotal + pricing.cleaning_fee,
                created_at=_at(check_in - timedelta(days=rng.randint(3, 40))),
            )
        )
        check_in = check_out + timedelta(days=rng.randint(0, 9))


def _at(day: date) -> datetime:
    return datetime.combine(day, time(12), tzinfo=UTC)


async def add_past_stays(session: AsyncSession, rng: random.Random) -> int:
    has_history = exists().where(
        Booking.listing_id == Listing.id, Booking.status == BookingStatus.COMPLETED
    )
    rows = await session.execute(
        select(Listing, ListingPricing)
        .join(ListingPricing, ListingPricing.listing_id == Listing.id)
        .where(Listing.is_listed, ~has_history)
        .order_by(Listing.id)
    )
    added = 0
    for listing, pricing in rows:
        stays = past_stays(listing, pricing, rng)
        session.add_all(stays)
        added += len(stays)
    return added


async def main(seed: int) -> None:
    db = Database(get_settings().database_url)
    async with db.sessions.begin() as session:
        added = await add_past_stays(session, random.Random(seed))
    await db.dispose()
    print(f"Added {added} past stays.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--seed", type=int, default=42)
    asyncio.run(main(parser.parse_args().seed))
