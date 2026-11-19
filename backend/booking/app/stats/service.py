"""Numbers for the host's dashboard, counted with plain SQL aggregations.

Only paid stays count: confirmed bookings and completed ones. Money and the number of
bookings go to the month of check-in; nights go to the month they fall in, so a stay
from 30 June to 3 July adds one night to June and two to July.
"""

import calendar
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal
from app.stats.schemas import HostStatsOut, MonthStats, TopListing

TOP_LISTINGS = 5

# The host's currencies in that year, the most used first.
CURRENCIES = text("""
    SELECT currency
    FROM bookings
    WHERE host_id = :host_id
      AND status IN ('confirmed', 'completed')
      AND lower(period) >= :year_start AND lower(period) < :year_end
    GROUP BY currency
    ORDER BY count(*) DESC
""")

REVENUE_BY_MONTH = text("""
    SELECT date_trunc('month', lower(period))::date AS month,
           count(*) AS bookings,
           sum(total) AS revenue
    FROM bookings
    WHERE host_id = :host_id
      AND status IN ('confirmed', 'completed')
      AND currency = :currency
      AND lower(period) >= :year_start AND lower(period) < :year_end
    GROUP BY 1
""")

# generate_series turns every stay into one row per night.
NIGHTS_BY_MONTH = text("""
    SELECT date_trunc('month', night)::date AS month, count(*) AS nights
    FROM bookings
    CROSS JOIN LATERAL generate_series(lower(period), upper(period) - 1, interval '1 day') AS night
    WHERE host_id = :host_id
      AND status IN ('confirmed', 'completed')
      AND period && daterange(:year_start, :year_end)
      AND night::date >= :year_start AND night::date < :year_end
    GROUP BY 1
""")

TOP_BY_REVENUE = text("""
    SELECT b.listing_id, l.title, count(*) AS bookings, sum(b.total) AS revenue
    FROM bookings AS b
    JOIN listings AS l ON l.id = b.listing_id
    WHERE b.host_id = :host_id
      AND b.status IN ('confirmed', 'completed')
      AND b.currency = :currency
      AND lower(b.period) >= :year_start AND lower(b.period) < :year_end
    GROUP BY b.listing_id, l.title
    ORDER BY revenue DESC
    LIMIT :top
""")

LISTED_PLACES = text("SELECT count(*) FROM listings WHERE host_id = :host_id AND is_listed")


async def host_stats(
    session: AsyncSession, host: Principal, year: int, currency: str | None
) -> HostStatsOut:
    params: dict[str, object] = {
        "host_id": host.user_id,
        "year_start": date(year, 1, 1),
        "year_end": date(year + 1, 1, 1),
    }
    currencies = list((await session.scalars(CURRENCIES, params)).all())
    currency = currency or (currencies[0] if currencies else "EUR")
    params["currency"] = currency

    money = {row.month: row for row in await session.execute(REVENUE_BY_MONTH, params)}
    nights = {row.month: row.nights for row in await session.execute(NIGHTS_BY_MONTH, params)}
    top = await session.execute(TOP_BY_REVENUE, {**params, "top": TOP_LISTINGS})
    # Occupancy is measured against the places listed now: simple, and close enough.
    places = await session.scalar(LISTED_PLACES, params) or 0

    months = []
    for number in range(1, 13):
        month = date(year, number, 1)
        row = money.get(month)
        days = calendar.monthrange(year, number)[1]
        months.append(
            MonthStats(
                month=month,
                bookings=row.bookings if row else 0,
                revenue=row.revenue if row else 0,
                nights=nights.get(month, 0),
                occupancy_percent=_percent(nights.get(month, 0), places * days),
            )
        )

    revenue = sum(m.revenue for m in months)
    bookings = sum(m.bookings for m in months)
    booked_nights = sum(m.nights for m in months)
    days_in_year = 366 if calendar.isleap(year) else 365
    return HostStatsOut(
        year=year,
        currency=currency,
        currencies=currencies,
        listed_places=places,
        revenue=revenue,
        bookings=bookings,
        average_booking=revenue // bookings if bookings else 0,
        nights=booked_nights,
        occupancy_percent=_percent(booked_nights, places * days_in_year),
        months=months,
        top_listings=[
            TopListing(
                listing_id=row.listing_id,
                title=row.title,
                bookings=row.bookings,
                revenue=row.revenue,
            )
            for row in top
        ],
    )


def _percent(part: int, whole: int) -> float:
    return round(100 * part / whole, 1) if whole else 0.0
