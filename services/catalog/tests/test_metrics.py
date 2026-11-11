import pytest
from django.urls import reverse
from prometheus_client import REGISTRY

from apps.listings.models import ListingStatus
from tests.factories import ListingFactory

pytestmark = pytest.mark.django_db


def sample(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def test_requests_are_counted_by_url_name(api_client):
    listing = ListingFactory(status=ListingStatus.PUBLISHED)
    ok = {"method": "GET", "route": "listing-detail", "status": "200"}
    before = sample("http_requests_total", **ok)

    api_client.get(reverse("listing-detail", args=[listing.pk]))
    api_client.get("/no/such/page")

    assert sample("http_requests_total", **ok) == before + 1
    assert sample("http_requests_total", method="GET", route="unmatched", status="404") >= 1
    assert sample("http_request_duration_seconds_count", method="GET", route="listing-detail") >= 1


def test_probes_are_not_counted(api_client):
    before = sample("http_requests_total", method="GET", route="healthz", status="200")

    api_client.get(reverse("healthz"))

    assert sample("http_requests_total", method="GET", route="healthz", status="200") == before


def test_metrics_endpoint_speaks_prometheus(api_client):
    api_client.get(reverse("amenities"))

    response = api_client.get(reverse("metrics"))

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain")
    assert b'http_requests_total{method="GET",route="amenities",status="200"}' in (response.content)


def test_gateway_request_id_is_echoed(api_client):
    response = api_client.get(reverse("amenities"), HTTP_X_REQUEST_ID="abc-123")

    assert response["X-Request-ID"] == "abc-123"


def test_unsafe_request_ids_are_replaced(api_client):
    response = api_client.get(reverse("amenities"), HTTP_X_REQUEST_ID="forged\nline")

    assert len(response["X-Request-ID"]) == 32
