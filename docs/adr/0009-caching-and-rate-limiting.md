# 9. Caching and rate limiting

Status: accepted

## Context

Reads dominate: search and listing pages are requested far more often than anything
changes. Public endpoints are also the easiest target for scrapers and floods, and
booking writes are expensive (row locks, payment provider calls).

## Decision

### Caching

| What | Where | Invalidation |
|---|---|---|
| Search result pages | Booking, Redis | TTL 30 s, key = hash of the normalised query |
| Public listing page | Catalog, Redis | Deleted when the listing's transaction commits; TTL 5 min |
| Calendar, quote, bookings | never cached | they must be exact |

- **Search** is cached by TTL only. Every booking changes availability, so event-based
  invalidation would empty the cache constantly; 30 seconds of lag is acceptable for a
  shop window because booking re-checks everything. List filters are sorted before
  hashing, so `amenities=wifi&amenities=pool` and the reverse share one entry. Responses
  carry `Cache-Control: public, max-age=30` and `X-Cache: HIT|MISS`.
- **Listing page** is the most read response of Catalog. Every change visible to guests
  already passes through `emit_listing_event` (ADR 4), which now also drops the cache
  entry `on_commit`. The TTL bounds the one remaining race: a reader that loaded the old
  row before the commit and stores it after the delete.
- Only successful responses are cached, so a listing published a moment after a 404 is
  visible at once.

### Rate limiting

- **Gateway**: Nginx `limit_req`, 20 requests/s per client address with a burst of 40.
  Cheap flood protection in front of everything.
- **Services**: Booking limits searches (60/min) and calendar/quote (120/min) per client
  address, and booking writes (create, pay, cancel) per user (20/min). Rates are
  settings, e.g. `SEARCH_RATE_LIMIT=60/minute`. Catalog keeps its DRF throttle on login
  and registration.
- **Algorithm: GCRA** in a Lua script in Redis. One key per client stores the
  theoretical arrival time; the check and the update are atomic across API workers. It
  allows a burst up to the limit and then refills smoothly, without the double burst a
  fixed window allows at its edge.
- **Responses**: 429 as Problem Details with `Retry-After` and `RateLimit-*` headers.
- **Client address**: Nginx is the edge, so it overwrites `X-Forwarded-For` with the
  connecting address instead of appending to it. Otherwise any client could send its own
  header and get a fresh budget per request (this also hardens Catalog's throttle).

### Failure mode

Cache and limiter **fail open**: if Redis is down or slow (0.5 s timeouts), requests are
served uncached and unlimited, and a warning is logged. Redis is an accelerator here,
not a dependency the API cannot work without.

## Consequences

- Behind a CDN or another proxy, the gateway must take the client address from that
  proxy's header instead of the TCP peer.
- Per-address limits treat users behind one NAT as one client; authenticated writes are
  limited per account instead.
