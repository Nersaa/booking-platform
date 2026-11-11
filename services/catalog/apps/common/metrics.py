"""Prometheus metrics, named like Booking's so one dashboard covers both services.

Gunicorn runs several workers, so in containers PROMETHEUS_MULTIPROC_DIR points to a
tmpfs where each process writes its values and the scrape merges them.
"""

import os
import time
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
    start_http_server,
)

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


def registry() -> CollectorRegistry:
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        merged = CollectorRegistry()
        multiprocess.MultiProcessCollector(merged)
        return merged
    return REGISTRY


def metrics_view(request: HttpRequest) -> HttpResponse:
    return HttpResponse(generate_latest(registry()), content_type=CONTENT_TYPE_LATEST)


def serve(port: int) -> None:
    """For processes without an HTTP server of their own (relay, consumer)."""
    start_http_server(port, registry=registry())


class MetricsMiddleware:
    """Outermost middleware. Requests are labelled by URL name (`listing-detail`), never
    by raw path, to keep the number of time series bounded."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path in UNMEASURED_PATHS:
            return self.get_response(request)
        started = time.perf_counter()
        response = self.get_response(request)
        match = request.resolver_match
        route = (match.view_name or match.route) if match else "unmatched"
        method = request.method or ""
        HTTP_LATENCY.labels(method, route).observe(time.perf_counter() - started)
        HTTP_REQUESTS.labels(method, route, str(response.status_code)).inc()
        return response
