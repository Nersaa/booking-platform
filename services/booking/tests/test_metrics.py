from datetime import date
from uuid import uuid4

from httpx import AsyncClient
from prometheus_client import REGISTRY

from app.listings.models import Listing
from tests.helpers import Headers, book


def sample(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


async def test_requests_are_counted_by_route_template(
    client: AsyncClient, priced_listing: Listing
) -> None:
    labels = {"method": "GET", "route": "/api/v1/listings/{listing_id}/calendar", "status": "200"}
    before = sample("http_requests_total", **labels)

    await client.get(f"/api/v1/listings/{priced_listing.id}/calendar")
    await client.get(f"/api/v1/listings/{uuid4()}/calendar")  # 404, same route

    assert sample("http_requests_total", **labels) == before + 1
    assert sample("http_requests_total", **{**labels, "status": "404"}) >= 1
    assert sample("http_request_duration_seconds_count", method="GET", route=labels["route"]) >= 2


async def test_unknown_paths_share_one_label_and_probes_are_not_counted(
    client: AsyncClient,
) -> None:
    before = sample("http_requests_total", method="GET", route="unmatched", status="404")
    probes = sample("http_requests_total", method="GET", route="/healthz", status="200")

    await client.get(f"/no/such/{uuid4()}")
    await client.get("/healthz")

    assert sample("http_requests_total", method="GET", route="unmatched", status="404") == (
        before + 1
    )
    assert sample("http_requests_total", method="GET", route="/healthz", status="200") == probes


async def test_booking_status_changes_are_counted(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> None:
    held = sample("booking_status_changes_total", status="pending_payment")
    cancelled = sample("booking_status_changes_total", status="cancelled")
    guest = auth(uuid4())

    booking = (await book(client, guest, priced_listing, next_monday)).json()
    await client.post(
        f"/api/v1/bookings/{booking['id']}/cancel",
        json={"reason": "changed plans"},
        headers={**guest, "Idempotency-Key": str(uuid4())},
    )

    assert sample("booking_status_changes_total", status="pending_payment") == held + 1
    assert sample("booking_status_changes_total", status="cancelled") == cancelled + 1


async def test_metrics_are_exposed_in_prometheus_format(client: AsyncClient) -> None:
    await client.get("/api/v1/listings")

    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert 'http_requests_total{method="GET",route="/api/v1/listings",status="200"}' in (
        response.text
    )
