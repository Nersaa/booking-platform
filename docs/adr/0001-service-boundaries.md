# 1. Two services split by consistency and load profile

Status: accepted

## Context

A booking platform has two very different halves. Content and people (accounts,
listings, photos, moderation, reviews) change rarely, are CRUD-heavy and need a
back-office. Dates and money (availability, prices, bookings, payments) take most of
the traffic, need strict consistency under concurrent writes and must stay up even
when the back-office is down.

## Decision

- **Catalog** (Django + DRF): identity and JWT issuing, listings, photos, moderation,
  reviews, notifications. Django Admin is the moderation desk.
- **Booking** (FastAPI, async): search, calendar, pricing, bookings, payments.
- Each service owns its database. Neither reads the other's tables.
- No synchronous service-to-service calls while handling a request. Booking keeps a
  read model of the listing fields it needs, updated from Catalog events.

## Consequences

- Booking keeps working (search and bookings) when Catalog is unavailable.
- Listing changes reach search with a small delay (eventual consistency).
- We need reliable event delivery: see the transactional outbox ADR (stage 2).
- Splitting further (auth, payments, notifications as separate services) was rejected:
  it would add deployment and consistency cost without a different load or data profile.
