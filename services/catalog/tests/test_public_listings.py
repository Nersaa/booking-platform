import pytest
from django.urls import reverse

from apps.listings import services
from apps.listings.models import Listing, ListingStatus, PhotoStatus
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


def test_listing_page_is_served_from_cache(api_client, django_assert_num_queries):
    listing = ListingFactory(status=ListingStatus.PUBLISHED, title="Old title")
    url = reverse("listing-detail", args=[listing.pk])
    api_client.get(url)
    Listing.objects.filter(pk=listing.pk).update(title="Changed behind the API")

    with django_assert_num_queries(0):
        response = api_client.get(url)

    assert response.data["title"] == "Old title"


def test_changing_a_listing_refreshes_its_cached_page(
    api_client, django_capture_on_commit_callbacks
):
    listing = ListingFactory(status=ListingStatus.PUBLISHED, title="Old title")
    url = reverse("listing-detail", args=[listing.pk])
    api_client.get(url)

    with django_capture_on_commit_callbacks(execute=True):
        services.listing_update(listing=listing, title="New title")

    assert api_client.get(url).data["title"] == "New title"


def test_missing_listings_are_not_cached(api_client):
    listing = ListingFactory(status=ListingStatus.PENDING_REVIEW)
    url = reverse("listing-detail", args=[listing.pk])
    assert api_client.get(url).status_code == 404

    services.listing_publish(listing=listing)

    assert api_client.get(url).status_code == 200
