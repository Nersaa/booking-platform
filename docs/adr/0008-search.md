# 8. Search: one PostGIS query over the Booking read model, keyset pages

Status: accepted

## Context

Guests search by map area or around a point, with dates, guest count, amenities, price
and rating, and expect the nearest or best results first. Search is the most frequent
request of the platform and must answer from data that already knows availability.

## Decision

- **Search lives in Booking.** It already holds a read model of every published listing
  (ADR 4), the prices and the calendar. One SQL query answers "where, what and when"
  without calling Catalog. `GET /api/v1/listings` is routed to Booking by the gateway;
  the listing page itself stays in Catalog.
- **Location is a generated column**:
  `location geography(Point, 4326) GENERATED ALWAYS AS (ST_MakePoint(lon, lat)) STORED`,
  with a GiST index. PostgreSQL derives it from the coordinates the events carry, so the
  two can never disagree. Map viewports use `ST_Intersects` with an envelope; a point
  search uses `ST_DWithin` and sorts by `ST_Distance`. Distances are in metres on the
  sphere, without projections.
- **Availability is two `NOT EXISTS` probes** into bookings and host blocks. They use the
  same GiST indexes on `(listing_id, period)` that enforce "no overlaps" (ADR 5, 6), and
  the same rule for what holds dates (`Booking.holds_dates()`). When dates are given, the
  stay is priced for the page's results only, with one query for seasonal rates.
- **Filters**: guests, property types (any of), amenities (all of, `@>` with a GIN
  index), bedrooms, country and city, rating, base nightly price. Prices are compared
  only within one currency, so price filters and the price sort require `currency`.
- **Keyset pagination.** Results are ordered by `(distance, id)`, `(price, id)` or
  `(rating, review_count, id)` descending. The response carries an opaque cursor with
  the last row's key and the sort it belongs to; the next page is
  `WHERE (key, id) > (:key, :id)`. No `OFFSET`, no `COUNT(*)`: deep pages cost the same
  as the first, and new listings never shift a page. The same helper pages the guest's
  and host's booking lists. A cursor from another sort is rejected with 400.
- **Cached for 30 seconds** (ADR 9). Search is a shop window; the price and the dates
  are always checked again, under a lock, when booking.

## Consequences

- Search results lag Catalog edits by the event delay (well under a second) plus the
  cache TTL.
- No total count is returned. Map UIs page by viewport, so it is not missed; an
  approximate count can come from planner statistics later if needed.
- Ranking is deliberately simple (rating, then number of reviews). A relevance score can
  replace the sort key without changing the pagination.
