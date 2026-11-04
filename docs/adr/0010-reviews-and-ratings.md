# 10. Reviews from completed stays, ratings through events

Status: accepted

## Context

Ratings are only worth something if every review comes from a real stay, once. Reviews
are shown on the listing page (Catalog), while search sorts and filters by rating
(Booking).

## Decision

- **Reviews live in Catalog**, next to the listing page and the authors' names.
- **Eligibility comes from Booking.** After check-out, Booking's job completes the stay
  and publishes `booking.completed` (ADR 7). Catalog's consumer records a
  `ReviewableStay` and emails the guest an invitation. Only that guest can review that
  booking, once (one-to-one with the stay), within 14 days of check-out.
- **The rating is maintained, not computed per request.** Each listing keeps
  `review_count` and `rating_total`. A new review locks the listing row, adds its score
  and bumps the version in the same transaction, so concurrent reviews add up and the
  average is read without aggregation.
- **Booking learns the rating from listing events.** The listing snapshot gained
  `rating` and `review_count` (`booking-contracts` 1.1.0). The fields have defaults, so
  older events still parse and consumers can be upgraded in any order.
- Hosts can reply publicly once per review. Reviews are read-only in the admin: changing
  a score there would bypass the totals.

## Consequences

- A review changes the listing version, so it travels through the outbox and refreshes
  the cached listing page (ADR 9) and the search index like any other edit.
- Moderating or removing a review must go through a service that subtracts the score;
  there is none yet.
