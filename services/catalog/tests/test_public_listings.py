import pytest
from django.urls import reverse

from apps.listings.models import ListingStatus, PhotoStatus
from tests.factories import ListingFactory, PhotoFactory

pytestmark = pytest.mark.django_db


def test_amenities_are_seeded(api_client):
    response = api_client.get(reverse("amenities"))

    assert response.status_code == 200
    assert {"code": "wifi", "name": "Wi-Fi"} in response.data


@pytest.mark.parametrize(
    "status", [ListingStatus.DRAFT, ListingStatus.PENDING_REVIEW, ListingStatus.ARCHIVED]
)
def test_unpublished_listings_are_hidden(api_client, status):
    listing = ListingFactory(status=status)

    response = api_client.get(reverse("listing-detail", args=[listing.pk]))

    assert response.status_code == 404


def test_published_listing_exposes_only_public_data(api_client):
    listing = ListingFactory(status=ListingStatus.PUBLISHED)
    ready = PhotoFactory(listing=listing)
    PhotoFactory(listing=listing, status=PhotoStatus.PROCESSING)

    response = api_client.get(reverse("listing-detail", args=[listing.pk]))

    assert response.status_code == 200
    assert response.data["host"] == {"id": str(listing.host.pk), "first_name": "Alex"}
    assert "rejection_reason" not in response.data
    assert [photo["id"] for photo in response.data["photos"]] == [str(ready.pk)]
    assert response.data["photos"][0]["large_url"].endswith(f"{ready.pk}/large.webp")
