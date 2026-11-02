# 5. Availability and pricing model

Status: accepted

## Context

Booking answers "is this place free on these nights and what does the stay cost". The
answer must be exact (money) and stay correct under concurrent edits by the host and,
from stage 3, concurrent bookings.

## Decision

- Money is stored and returned as integers in minor units (cents) with an ISO 4217
  currency per listing. No floats anywhere in the price path.
- Periods are PostgreSQL `daterange` values, half-open `[start, end)`: `end` is the
  check-out day. Two stays can meet on a changeover day without overlapping.
- Seasonal rates and host blocks are protected by exclusion constraints
  (`EXCLUDE USING gist (listing_id WITH =, period WITH &&)`, needs `btree_gist`). The
  database rejects overlaps even when two requests race; the API maps that to 409.
  Stage 3 uses the same mechanism for bookings.
- Price of a night: seasonal rate, else weekend price (Friday and Saturday nights), else
  the regular price. A stay of 28+ nights gets the monthly discount, 7+ the weekly one;
  the discount is rounded down to a whole minor unit.
- The calculation is a pure function (`app/availability/pricing.py`), unit-tested without
  a database. The quote endpoint and, in stage 3, booking creation use the same function.
- A listing is bookable once it is published in Catalog and its host has set a price.

## Consequences

- Clients format money themselves (amount / 10^exponent of the currency).
- Calendar and quote need only a few indexed range queries per request.
