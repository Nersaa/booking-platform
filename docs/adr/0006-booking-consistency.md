# 6. Booking consistency: holds, exclusion constraint, idempotency

Status: accepted

## Context

The one thing a booking platform must never do is sell the same night twice. Requests
race (two guests, one host closing dates), clients retry after timeouts, and guests
double-click. Payment takes minutes, so dates must be held while the guest pays.

## Decision

- **Hold, then confirm.** Creating a booking prices the stay and holds the dates in
  `pending_payment` for 15 minutes (`hold_expires_at`). A successful payment moves it to
  `confirmed`; otherwise a worker job moves it to `expired`. All transitions go through
  one table of allowed moves: `pending_payment -> confirmed | expired | cancelled`,
  `confirmed -> cancelled | completed`.
- **The database is the last line of defence.** `bookings` has
  `EXCLUDE USING gist (listing_id WITH =, period WITH &&) WHERE status IN
  ('pending_payment', 'confirmed')`. Whatever the code does, two active bookings of one
  listing cannot share a night; a violation becomes 409 `dates_unavailable`.
- **One lock per listing.** Booking creation and host blocks lock the listing row
  (`SELECT ... FOR UPDATE`) before checking blocks and bookings, because a constraint
  cannot span the two tables. The lock covers one listing only, so different listings
  never wait for each other.
- **Stale holds do not block.** Calendar and quote ignore holds past their time, and
  booking creation expires them for that listing before inserting, so a slow sweeper
  never keeps dates hostage.
- **Idempotency keys.** Unsafe endpoints (create, pay, cancel) require an
  `Idempotency-Key` header. The key is inserted in the same transaction as the operation,
  with the response stored at the end:
  - a retry gets the stored response (`Idempotent-Replayed: true`);
  - a concurrent duplicate waits on the key's primary key and then replays;
  - the same key with a different body is rejected with 422;
  - a failed request rolls back its key, so the client can simply retry.
  Keys are scoped per user and purged after 24 hours.
- **Money is fixed at booking time.** The booking stores the quoted subtotal, discount,
  cleaning fee and total; later price changes do not affect it.

## Consequences

- Correctness under concurrency is proven by tests that fire parallel requests (8 guests
  for the same dates produce exactly one booking).
- Holding a listing lock serialises bookings of one listing; at realistic traffic per
  listing this is not a bottleneck.
