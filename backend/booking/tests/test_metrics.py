from datetime import date
from uuid import uuid4

from httpx import AsyncClient
from prometheus_client import REGISTRY

from app.listings.models import Listing
from tests.helpers import Headers, book


async def test_metrics_endpoint_reports_requests(
    client: AsyncClient, priced_listing: Listing
) -> None:
    await client.get(f"/api/v1/listings/{priced_listing.id}/calendar")

    response = await client.get("/metrics")

    assert response.status_code == 200
    # The instrumentator registers its metrics once per process, while every test builds
    # a new app, so only the metric families are checked here.
    assert "http_request_duration_seconds_bucket{" in response.text
    assert "booking_status_changes_total" in response.text


async def test_booking_status_changes_are_counted(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> None:
    def changes(status: str) -> float:
        labels = {"status": status}
        return REGISTRY.get_sample_value("booking_status_changes_total", labels) or 0.0

    held, cancelled = changes("pending_payment"), changes("cancelled")
    guest = auth(uuid4())

    booking = (await book(client, guest, priced_listing, next_monday)).json()
    await client.post(f"/api/v1/bookings/{booking['id']}/cancel", json={}, headers=guest)

    assert changes("pending_payment") == held + 1
    assert changes("cancelled") == cancelled + 1
