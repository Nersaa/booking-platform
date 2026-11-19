# Architecture notes

Short answers to "why is it built this way?". Each section names the code to look at.

## Two services

| | Catalog | Booking |
|---|---|---|
| Framework | Django + DRF | FastAPI (async) |
| Owns | users, JWT, listings, photos, moderation, reviews, emails | search, prices, calendar, bookings, payments |
| Database | PostgreSQL `catalog` | PostgreSQL `booking` with PostGIS |

Django gives the CRUD-heavy part an admin panel, auth and migrations for free. Booking
handles the busy path (search and booking), where async I/O pays off. Each service has
its own database and never reads the other's tables.

## Login between services

Catalog signs access tokens with a private RSA key (RS256) and publishes the public key
at `/.well-known/jwks.json`. Booking checks tokens itself with that public key
(`PyJWKClient` caches it), so it never calls Catalog to authenticate a request.

Code: `backend/catalog/apps/users/tokens.py`, `backend/booking/app/auth.py`.

## Events instead of HTTP calls

Booking needs listing data (title, location, capacity) and Catalog needs to know about
bookings to send emails. They exchange events through RabbitMQ:

- Catalog → `listing.published / updated / archived` with a full copy of the listing.
  Booking stores it in its own `listings` table and applies an event only if its
  `version` is newer, so duplicates and late messages do no harm.
- Booking → `booking.confirmed / cancelled / completed`. Catalog sends emails and, after a
  completed stay, lets the guest leave a review.

**Outbox.** An event is first saved in an `outbox` table in the same transaction as the
change, then sent to RabbitMQ by a background job: a Celery beat task every second in
Catalog, a loop in the Booking worker. So an event is never lost if RabbitMQ is down, and
never sent for a change that was rolled back. Consumers may get an event twice and
ignore repeats (by `version`, or by remembering processed event ids).

Event schemas are shared Pydantic models in `backend/contracts`.

## No double bookings

The key rule: one night can't be sold twice. PostgreSQL enforces it with an exclusion
constraint, so it holds even when two requests arrive at the same moment:

```sql
EXCLUDE USING gist (listing_id WITH =, period WITH &&)
WHERE (status IN ('awaiting_host', 'pending_payment', 'confirmed'))
```

`period` is a `daterange` `[check_in, check_out)`. A new booking holds the dates for
15 minutes while the guest pays; a worker job expires unpaid holds.

## Booking requests

A host can turn instant booking off for a place (`instant_book` in its pricing). A
booking then starts as `awaiting_host`: the dates are held for 24 hours, and the guest
cannot pay yet. The host accepts (the booking moves to `pending_payment` with 24 hours to
pay) or declines (`declined`, the dates are free). Both answers lock the booking row and
check the deadline, so an answer after it fails even if the worker has not expired the
request yet.

The same worker job that expires unpaid holds expires unanswered requests. It does that
with `UPDATE ... RETURNING`, so it knows which requests expired and writes a
`booking.request_expired` event for each; Catalog turns these events
(`booking.requested`, `.accepted`, `.declined`, `.request_expired`) into emails. A double click or a
race simply gets `409 dates_unavailable`. Tests fire 8 parallel bookings for the same
dates and expect exactly one to succeed.

Code: `backend/booking/app/bookings/`.

## Payments

The payment provider is a small Stripe-like mock (`backend/payment-mock`). Booking
creates a payment with a description and a `return_url`, and the guest pays on the
provider's checkout page with a test card. Only test card numbers are accepted, so a
real card is never typed into the demo. The provider then sends the guest back to the
booking's page on the website.

The result itself comes back separately, as a webhook signed with HMAC-SHA256, which
Booking verifies (and rejects old timestamps to stop replays). Each webhook is processed
once (`processed_webhooks`). The redirect only brings the guest back: the booking page
keeps checking the status until the webhook has confirmed the booking.

Refunds follow the cancellation policy (host cancels: full refund; guest: full 7+ days
before check-in, half up to the day before, none on the day) and are sent to the
provider during the cancellation. If the provider is down, the cancellation returns 503
and can simply be repeated.

## Search

`GET /api/v1/listings` filters by map area or distance (PostGIS), dates, guests, amenities,
price and rating, in one SQL query over Booking's copy of the listings. Free dates are
checked with the same rules as booking. Results are paginated with `limit` and `offset`
and cached in Redis for 30 seconds.

Code: `backend/booking/app/search/`.

## Caching and rate limits

- Search results: Redis, 30 seconds. Listing page in Catalog: Redis, cleared when the
  listing changes. Prices, calendar and bookings are never cached.
- Booking limits requests per client per minute with a counter in Redis
  (`app/ratelimit.py`); Catalog uses DRF throttling on login and registration. If Redis is
  down, both the cache and the limiter are skipped instead of failing requests.

## Monitoring

Both APIs expose Prometheus metrics (`prometheus-fastapi-instrumentator`,
`django-prometheus`), plus a counter of booking status changes. Prometheus scrapes them
and RabbitMQ; Grafana shows the "Booking Platform" dashboard. Both are configured from
files in `infra/`.

## Support

Users open a request on the website (topic, subject, message, optionally a booking) and
can keep writing until it is closed. Staff work in Django Admin, "Support requests":
filter by status, read the conversation, type a reply and save. The reply is stored as
a message, the request becomes "Answered" and the user gets an email (Celery).

The status always shows whose turn it is: `open` waits for support, `answered` for the
user, `closed` takes no more messages. Code: `backend/catalog/apps/support/`.

## Host statistics

`GET /api/v1/host/stats` is counted in SQL, not in Python (`app/stats/service.py`):

- revenue and bookings by month: `GROUP BY date_trunc('month', lower(period))`;
- nights by month: `generate_series` turns each stay into one row per night, so a stay
  over the end of a month is split between both months;
- occupancy: booked nights / (listed places x days in the month);
- best places: the bookings joined with the listings read model, `ORDER BY revenue`.

Only paid stays count (`confirmed`, `completed`), in one currency at a time. For the demo
`python -m app.demo_stays` adds a year of completed stays (about 12 500 rows); the
endpoint answers in under 100 ms.

## Messages between guest and host

Messages belong to a booking, so they live in Booking next to it (`booking_messages`).
Only the booking's guest and host can read or write them, the same check as for the
booking itself. Booking knows people only by id, so a message stores its author's id and
the API says whether it came from the host. The website reads new messages every
10 seconds.

## Website

`frontend/` is a small React + TypeScript app (Vite). It is built into static files and
served by its own Nginx container; the gateway sends `/api`, `/admin`, `/media` and
`/storage` to the backend and everything else to the site, so the browser talks to one
origin and no CORS setup is needed.

- Photo uploads: the page asks Catalog for a presigned POST, sends the file with
  `FormData` to `/storage/...` (object storage behind the gateway, POST only), confirms
  the upload and re-reads the listing every 2 seconds while a photo is still processing.
- A host's place lives in two services: details and photos in Catalog, prices and closed
  dates in Booking. Booking learns about a place from the "published" event, so the
  prices form appears only for published places and retries for a few seconds right
  after publishing.

- Requests go through one helper (`src/api/client.ts`) that adds the JWT and, when the
  access token has expired, gets a new one with the refresh token and repeats the
  request.
- Tokens are kept in `localStorage`. It is the simplest option for a demo; a production
  site would rather keep the refresh token in an `HttpOnly` cookie, out of reach of
  scripts.
- Server data is loaded with TanStack Query. "My bookings" re-reads the list every
  3 seconds while a payment is pending, because the result reaches the backend as a
  webhook, not through the browser.
