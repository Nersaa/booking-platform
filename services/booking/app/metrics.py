"""Prometheus metrics.

HTTP metrics use the same names in every service (`http_requests_total`,
`http_request_duration_seconds`), so one dashboard and one set of alerts covers them all.

The API runs several worker processes, so in containers PROMETHEUS_MULTIPROC_DIR points
to a tmpfs where each process writes its values and the scrape merges them.
"""

import os
import time
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Probes and scrapes would only add noise to the request rate.
UNMEASURED_PATHS = frozenset({"/metrics", "/healthz", "/readyz"})

HTTP_REQUESTS = Counter(
    "http_requests_total", "HTTP requests handled.", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Time to produce the response.",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
BOOKING_STATUS_CHANGES = Counter(
    "booking_status_changes_total", "Bookings entering a status.", ["status"]
)
SEARCH_CACHE = Counter("search_cache_requests_total", "Search cache lookups.", ["result"])
RATE_LIMITED = Counter("rate_limited_requests_total", "Requests refused with 429.", ["scope"])
EVENTS_CONSUMED = Counter(
    "events_consumed_total", "Events received from the broker.", ["event_type", "result"]
)
OUTBOX_PUBLISHED = Counter("outbox_published_events_total", "Events relayed to the broker.")
OUTBOX_PENDING = Gauge(
    "outbox_pending_events", "Events waiting to be published.", multiprocess_mode="max"
)
OUTBOX_OLDEST_AGE = Gauge(
    "outbox_oldest_pending_seconds",
    "Age of the oldest unpublished event: how far other services lag behind.",
    multiprocess_mode="max",
)
JOB_FAILURES = Counter("background_job_failures_total", "Failed background job runs.", ["name"])


def registry() -> CollectorRegistry:
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        merged = CollectorRegistry()
        multiprocess.MultiProcessCollector(merged)  # type: ignore[no-untyped-call]
        return merged
    return REGISTRY


async def metrics_endpoint(_: Request) -> Response:
    return Response(generate_latest(registry()), media_type=CONTENT_TYPE_LATEST)


class MetricsMiddleware:
    """Pure ASGI, so streaming responses and background tasks are not affected.

    Requests are labelled by route template (`/api/v1/bookings/{booking_id}`), never by
    raw path, to keep the number of time series bounded.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in UNMEASURED_PATHS:
            await self.app(scope, receive, send)
            return

        status = 500
        started = time.perf_counter()

        async def send_with_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            # The router records the matched route in the scope; unknown paths share one label.
            route: Any = scope.get("route")
            template = route.path if route is not None else "unmatched"
            method = scope["method"]
            HTTP_LATENCY.labels(method, template).observe(time.perf_counter() - started)
            HTTP_REQUESTS.labels(method, template, str(status)).inc()
