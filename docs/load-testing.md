# Load testing

## Scenario

[`loadtest/locustfile.py`](../loadtest/locustfile.py) models a marketplace on a busy
evening:

| User | Share | Does |
|---|---|---|
| Browser | 90% | searches the map (with and without dates), around a point; opens listing pages, calendars and quotes |
| Booker | 10% | registers, searches with dates, books one of the top results, pays on the provider's page, lists own bookings |

Dates cluster around a few popular weekends, and bookers prefer the top five results.
Many of them race for the same nights on purpose: a 409 "dates taken" is the correct
answer and is counted as a success. What must never happen is two active bookings
sharing a night.

Every request goes through the full path: Nginx → service → PostgreSQL/Redis, with events
through the outbox and RabbitMQ, payment webhooks from the provider mock and emails via
Celery.

## How to run

```bash
make loadtest-up                         # the stack with abuse limits lifted
make seed                                # 300 published, priced listings in 8 cities
make loadtest                            # 200 users, 5 minutes; USERS, SPAWN_RATE, RUN_TIME override
```

Load test mode lifts the per-address rate limits (all traffic comes from one generator,
so they would measure the limiter, not the system). The report is written to
`loadtest/results/report.html`. Watch it live in Grafana at http://localhost:3000. Return
to normal limits with `docker compose up -d`.

## Results

Measured on 5 November 2026, the whole stack (16 containers) and Locust on one desktop:
Intel Core i7-10700K (8 cores, 16 threads), 64 GB RAM, Docker Desktop on Windows 11.
300 listings in 8 cities. Default service sizes: Booking API 2 uvicorn workers, Catalog
API 3 gunicorn workers. Times are in milliseconds, as seen by the client (Locust).

### Run 1: a busy evening, 200 users, 5 minutes

**101 requests/s, 30,366 requests, 0 failures, p95 13 ms.**

| Request | Count | p50 | p95 | p99 |
|---|---:|---:|---:|---:|
| Search, map + dates | 6,992 | 4 | 13 | 17 |
| Search, map | 6,256 | 3 | 6 | 10 |
| Search, nearby | 1,511 | 3 | 7 | 10 |
| Listing page (Catalog, cached) | 6,155 | 3 | 6 | 9 |
| Calendar | 3,160 | 8 | 11 | 14 |
| Quote | 3,071 | 7 | 10 | 13 |
| Book | 828 | 14 | 20 | 24 |
| Start payment | 750 | 14 | 20 | 26 |
| Own bookings | 853 | 6 | 8 | 10 |

The request rate is set by the users' think time (1 to 5 s), not by the system.

### Run 2: stress, 1,000 users, 4 minutes

**457 requests/s (Booking API peak 386/s), 109,430 requests, no 5xx, p95 630 ms.**

| Request | Count | p50 | p95 | p99 |
|---|---:|---:|---:|---:|
| Search, map + dates | 26,318 | 20 | 680 | 1,100 |
| Search, map | 23,563 | 19 | 680 | 1,000 |
| Listing page (Catalog, cached) | 22,602 | 6 | 64 | 250 |
| Calendar | 11,369 | 30 | 730 | 1,100 |
| Quote | 11,482 | 29 | 720 | 1,100 |
| Book | 2,302 | 68 | 860 | 1,200 |
| Start payment | 1,419 | 80 | 890 | 1,200 |

Two "provider: pay" calls failed with a dropped connection: the single-process payment
mock gave out, not the platform. Those two holds simply expire.

### What held

| Check | Run 1 | Run 2 |
|---|---|---|
| 5xx responses | 0 | 0 |
| Holds created / confirmed by payment webhook | 750 / 750 | 1,419 / 1,417 |
| Booking attempts refused with 409 (dates taken) | 78 | 883 |
| Two active bookings sharing a night (SQL check after the run) | **0** | **0** |
| Search cache hit ratio | 92.6% | 96.9% |
| Longest outbox lag (oldest unpublished event) | 0.44 s | 0.56 s |
| Messages in dead-letter queues | 0 | 0 |

Under contention the platform refuses bookings instead of selling a night twice, and
events keep flowing in well under a second.

### Where the limit is

In run 2, Booking's own histogram puts p95 at **128 ms** (p99 239 ms). Nginx measured
**430 ms** to the upstream, and Locust measured 630 ms. The difference is time spent
waiting before the handler runs: the two uvicorn workers of the Booking API are
CPU-bound at about 390 requests/s on this machine. The database is not the bottleneck:
the handlers stay fast while requests wait in front of them. The rest of the client-side
latency is the single Locust process driving 1,000 users.

Catalog, with its cached listing page, stays at a p95 of 5 ms on the server.

Next steps, in order of value:

1. Run more Booking API workers or replicas behind the gateway; the API is stateless.
2. Serve repeated searches from the gateway cache (Nginx `proxy_cache`, 30 s). Search
   results are already public and cacheable for 30 s.
3. Distribute Locust (master and workers) to push past ~500 requests/s from one machine.
