# Backend

Three Python services and one shared package. Each service is its own
[uv](https://docs.astral.sh/uv/) project with its own dependencies, tests and Dockerfile.

```
backend/
  catalog/          Django + DRF
  booking/          FastAPI
  payment-mock/     FastAPI, a stand-in for a real payment provider
  contracts/        Pydantic schemas of the events between catalog and booking
```

## catalog: users, listings and everything around them

| Folder | Responsible for |
|---|---|
| `config/` | Django settings, URLs, Celery app |
| `apps/users/` | registration, login, JWT tokens (RS256) and the public key at `/.well-known/jwks.json` |
| `apps/listings/` | listings, moderation (Django Admin), photo uploads to S3 and their processing in Celery, demo data (`seed_listings`, `seed_photos`) |
| `apps/reviews/` | reviews after a stay, host replies, the listing rating |
| `apps/support/` | help requests from users; staff answer them in Django Admin |
| `apps/favorites/` | listings users saved for later |
| `apps/notifications/` | reads booking events from RabbitMQ and sends emails |
| `apps/outbox/` | saves events with the change and sends them to RabbitMQ (Celery beat task) |
| `apps/common/` | shared pieces: error format, pagination, health checks, S3 helpers |
| `tests/` | pytest + pytest-django on a real PostgreSQL (Testcontainers) |

Inside an app: `models.py` (tables), `services.py` (business logic: all changes go
through here), `views.py` + `serializers.py` (HTTP), `tasks.py` (Celery).

## booking: search, prices and bookings

| Folder / file | Responsible for |
|---|---|
| `app/main.py` | the FastAPI app: routers, middleware, startup |
| `app/worker.py`, `app/jobs.py` | the worker process: reads listing events, sends booking events, expires unpaid holds and unanswered requests, completes stays |
| `app/listings/` | Booking's own copy of the listings, updated from Catalog's events |
| `app/search/` | `GET /api/v1/listings`: map, dates and filters in one PostGIS query |
| `app/availability/` | host prices, seasonal rates, closed dates; calendar and price quotes |
| `app/bookings/` | bookings and their statuses (instant or a request to the host), cancellation policy, guest-host messages |
| `app/stats/` | the host's statistics: revenue, bookings and occupancy by month, in plain SQL |
| `app/demo_stays.py` | a year of past stays for the demo (development only) |
| `app/payments/` | payment provider client, signed webhooks, refunds |
| `app/auth.py` | checks Catalog's JWTs with its public key |
| `app/ratelimit.py`, `app/cache.py` | request limits and the search cache in Redis |
| `migrations/` | Alembic database migrations |
| `tests/` | pytest on real PostgreSQL + PostGIS and Redis (Testcontainers) |

Inside a module: `models.py` (SQLAlchemy tables), `schemas.py` (Pydantic request and
response models), `service.py` (logic), `router.py` (HTTP endpoints).

## payment-mock

One file, `payment_mock/main.py`: creates payments, shows a checkout page with "Pay" and
"Decline", sends signed webhooks to Booking and accepts refunds. Data lives in memory.

## contracts

`src/contracts/`: event schemas (`listings.py`, `bookings.py`) and exchange names
(`topology.py`). Both services install this package, so producer and consumer always
agree on the format.

## Working on a service

```bash
cd backend/booking         # or catalog, payment-mock
uv sync                    # creates .venv with all dependencies
uv run python -m pytest    # needs Docker: tests start their own databases
uv run python -m mypy .
```

Lint and format the whole repository from its root: `make lint`, `make format`.
