# 11. Observability: metrics, dashboards, alerts, request ids

Status: accepted

## Context

The platform is several processes talking through a broker. When something goes wrong,
the questions are "is it slow or failing, and where?" and "are events flowing?", and they
must be answerable without attaching a debugger to production.

## Decision

- **Prometheus metrics in every process.** The two APIs export the same RED metrics,
  `http_requests_total{method, route, status}` and `http_request_duration_seconds`, so
  one dashboard and one set of alerts covers both. Routes are labelled by template
  (Booking) or URL name (Catalog), never by raw path, which keeps the number of series
  bounded. Probes and scrapes are not counted.
- **Business and pipeline metrics** where the work happens:
  - `booking_status_changes_total{status}`: holds, confirmations, expiries, cancellations;
  - `search_cache_requests_total{result}`: cache hits and misses;
  - `rate_limited_requests_total{scope}`: requests refused with 429;
  - `outbox_pending_events` and `outbox_oldest_pending_seconds`: how far other services lag
    behind;
  - `outbox_published_events_total`, `events_consumed_total{event_type, result}`;
  - `background_job_failures_total{name}`.

  RabbitMQ queue depth comes from its built-in Prometheus plugin.
- **Multi-process collection.** Gunicorn and uvicorn run several workers. Each process
  writes its values to `PROMETHEUS_MULTIPROC_DIR`, a tmpfs cleared on restart, and the
  `/metrics` handler merges them. Processes without an HTTP server (outbox relays, event
  consumers, the Booking worker) serve metrics on port 9100.
- **`/metrics` is internal.** Prometheus scrapes it inside the Docker network; the gateway
  answers 404.
- **Alerts** (`infra/prometheus/alerts.yml`):
  - a target is down;
  - more than 5% 5xx;
  - p95 latency above 1 s;
  - the oldest unpublished event is older than 60 s;
  - a dead-letter queue is not empty;
  - a background job keeps failing.

  They are evaluated by Prometheus; routing them to people (Alertmanager, on-call) is a
  deployment concern.
- **Grafana** is provisioned from files: the datasource and the "Booking Platform"
  dashboard (traffic, latency, errors, bookings, cache, rate limits, outbox lag,
  queues). Changes go through the repository, not the UI.
- **Request ids and JSON logs.** Nginx gives every request an `X-Request-ID` (`$request_id`),
  writes it into its JSON access log and passes it on. The services log it with every
  line and return it in the response. Event consumers use the event id instead, so a
  booking can be followed from the HTTP request through the outbox to the email. A
  request id sent by a client is accepted only if it is short and plain, so it cannot
  forge log lines.

## Consequences

- Metrics are pulled, so a crashed process shows up as `up == 0` rather than as silence.
- Logs go to stdout as JSON lines, ready for any collector (Loki, ELK); none is bundled.
- Tracing (OpenTelemetry) would add per-request timing across services. The request id
  covers correlation until that is worth its cost.
