import pytest
from django.urls import reverse

from apps.listings.models import ListingStatus
from tests.factories import ListingFactory, PhotoFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_user_saves_and_removes_a_listing(client_for):
    listing = ListingFactory(status=ListingStatus.PUBLISHED, title="Loft")
    PhotoFactory(listing=listing)
    client = client_for(UserFactory())
    url = reverse("favorite", args=[listing.pk])

    saved = client.put(url)
    again = client.put(url)  # saving twice changes nothing
    listed = client.get(reverse("favorites"))
    removed = client.delete(url)
    after = client.get(reverse("favorites"))

    assert saved.status_code == again.status_code == 204
    [item] = listed.data
    assert item["id"] == str(listing.pk)
    assert item["title"] == "Loft"
    assert item["cover_url"].endswith("/thumb.webp")
    assert removed.status_code == 204
    assert after.data == []


def test_favorites_are_private(client_for):
    listing = ListingFactory(status=ListingStatus.PUBLISHED)
    client_for(UserFactory()).put(reverse("favorite", args=[listing.pk]))

    assert client_for(UserFactory()).get(reverse("favorites")).data == []


def test_only_published_listings_can_be_saved_or_shown(client_for):
    draft = ListingFactory(status=ListingStatus.DRAFT)
    published = ListingFactory(status=ListingStatus.PUBLISHED)
    client = client_for(UserFactory())
    client.put(reverse("favorite", args=[published.pk]))
    published.status = ListingStatus.ARCHIVED
    published.save()

    assert client.put(reverse("favorite", args=[draft.pk])).status_code == 404
    assert client.get(reverse("favorites")).data == []


def test_favorites_need_a_login(api_client):
    assert api_client.get(reverse("favorites")).status_code == 401
