import pytest
from django.urls import reverse

from apps.listings.models import Listing, ListingStatus
from tests.factories import HostFactory, ListingFactory, PhotoFactory, UserFactory

pytestmark = pytest.mark.django_db

LISTINGS_URL = reverse("host-listings-list")


def detail_url(listing: Listing) -> str:
    return reverse("host-listings-detail", args=[listing.pk])


def listing_payload(**overrides):
    payload = {
        "title": "Cozy house with a garden",
        "description": "Quiet place 10 minutes from the beach.",
        "property_type": "house",
        "country": "es",
        "city": "Valencia",
        "address": "Calle Mayor 1",
        "latitude": "39.469907",
        "longitude": "-0.376288",
        "max_guests": 5,
        "bedrooms": 2,
        "beds": 3,
        "bathrooms": 1,
        "amenities": ["wifi", "parking"],
    }
    return payload | overrides


def test_guest_cannot_create_listing(client_for):
    response = client_for(UserFactory()).post(LISTINGS_URL, listing_payload())

    assert response.status_code == 403


def test_host_creates_draft_listing(client_for):
    host = HostFactory()

    response = client_for(host).post(LISTINGS_URL, listing_payload())

    assert response.status_code == 201
    assert response.data["status"] == ListingStatus.DRAFT
    assert response.data["country"] == "ES"
    assert {a["code"] for a in response.data["amenities"]} == {"wifi", "parking"}
    assert Listing.objects.get(pk=response.data["id"]).host == host


@pytest.mark.parametrize(
    "overrides",
    [
        {"latitude": "91.000000"},
        {"country": "ESP"},
        {"max_guests": 0},
        {"amenities": ["teleport"]},
    ],
)
def test_create_rejects_invalid_data(client_for, overrides):
    response = client_for(HostFactory()).post(LISTINGS_URL, listing_payload(**overrides))

    assert response.status_code == 400


def test_host_sees_only_own_listings(client_for):
    own = ListingFactory()
    foreign = ListingFactory()
    client = client_for(own.host)

    listed = client.get(LISTINGS_URL)
    foreign_detail = client.get(detail_url(foreign))

    assert [item["id"] for item in listed.data["results"]] == [str(own.pk)]
    assert foreign_detail.status_code == 404


def test_update_increments_version(client_for):
    listing = ListingFactory()

    response = client_for(listing.host).patch(detail_url(listing), {"title": "Renamed"})

    listing.refresh_from_db()
    assert response.status_code == 200
    assert listing.title == "Renamed"
    assert listing.version == 2


def test_listing_under_review_cannot_be_edited(client_for):
    listing = ListingFactory(status=ListingStatus.PENDING_REVIEW)

    response = client_for(listing.host).patch(detail_url(listing), {"title": "Sneaky edit"})

    assert response.status_code == 409
    assert response.json()["code"] == "invalid_state_transition"


def test_submit_requires_a_processed_photo(client_for):
    listing = ListingFactory()
    url = reverse("host-listings-submit", args=[listing.pk])

    without_photo = client_for(listing.host).post(url)
    PhotoFactory(listing=listing)
    with_photo = client_for(listing.host).post(url)

    assert without_photo.status_code == 400
    assert with_photo.status_code == 200
    assert with_photo.data["status"] == ListingStatus.PENDING_REVIEW


def test_only_drafts_can_be_deleted(client_for):
    draft = ListingFactory()
    published = ListingFactory(host=draft.host, status=ListingStatus.PUBLISHED)
    client = client_for(draft.host)

    assert client.delete(detail_url(draft)).status_code == 204
    assert client.delete(detail_url(published)).status_code == 409
    assert not Listing.objects.filter(pk=draft.pk).exists()


def test_archive_hides_listing_from_host_list(client_for):
    listing = ListingFactory(status=ListingStatus.PUBLISHED)
    client = client_for(listing.host)

    response = client.post(reverse("host-listings-archive", args=[listing.pk]))

    assert response.status_code == 200
    assert response.data["status"] == ListingStatus.ARCHIVED
    assert client.get(LISTINGS_URL).data["results"] == []
