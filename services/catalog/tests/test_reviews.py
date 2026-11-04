import uuid
from datetime import timedelta
from decimal import Decimal
from typing import cast

import pytest
from contracts import ListingEvent, ListingEventType
from django.urls import reverse
from django.utils import timezone

from apps.listings.models import Listing, ListingStatus
from apps.outbox.models import OutboxEvent
from apps.reviews.models import Review, ReviewableStay
from apps.users.models import User
from tests.factories import HostFactory, ListingFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def listing():
    return ListingFactory(status=ListingStatus.PUBLISHED, host=HostFactory(first_name="Hanna"))


def finished_stay(
    listing: Listing, guest: User | None = None, *, days_since_check_out: int = 1
) -> ReviewableStay:
    check_out = timezone.localdate() - timedelta(days=days_since_check_out)
    return ReviewableStay.objects.create(
        booking_id=uuid.uuid4(),
        listing=listing,
        guest=guest or cast(User, UserFactory(first_name="Gil")),
        check_in=check_out - timedelta(days=3),
        check_out=check_out,
        review_deadline=check_out + timedelta(days=14),
    )


def post_review(client_for, stay, *, rating=5, text="Lovely place", user=None):
    return client_for(user or stay.guest).post(
        reverse("reviews"),
        {"booking_id": str(stay.booking_id), "rating": rating, "text": text},
    )


def test_guest_reviews_a_finished_stay_and_the_rating_is_announced(listing, client_for):
    first = finished_stay(listing)
    second = finished_stay(listing)

    assert post_review(client_for, first, rating=5).status_code == 201
    response = post_review(client_for, second, rating=4, text="Good")

    assert response.status_code == 201
    assert response.data["author"]["first_name"] == "Gil"
    listing.refresh_from_db()
    assert listing.review_count == 2
    assert listing.rating == Decimal("4.50")
    events = [ListingEvent.model_validate(e.payload) for e in OutboxEvent.objects.all()]
    assert {e.event_type for e in events} == {ListingEventType.UPDATED}
    latest = max(events, key=lambda e: e.listing.version)
    assert latest.listing.rating == Decimal("4.50")
    assert latest.listing.review_count == 2


def test_rating_is_shown_on_the_listing_page(listing, client_for, api_client):
    post_review(client_for, finished_stay(listing), rating=4)

    response = api_client.get(reverse("listing-detail", args=[listing.pk]))

    assert response.data["rating"] == "4.00"
    assert response.data["review_count"] == 1


def test_only_the_guest_of_the_stay_can_review_it(listing, client_for):
    stay = finished_stay(listing)

    response = post_review(client_for, stay, user=UserFactory())

    assert response.status_code == 404
    assert not Review.objects.exists()


def test_a_stay_is_reviewed_once(listing, client_for):
    stay = finished_stay(listing)
    post_review(client_for, stay)

    response = post_review(client_for, stay, rating=1)

    assert response.status_code == 409
    assert response.data["code"] == "already_reviewed"
    listing.refresh_from_db()
    assert listing.review_count == 1


def test_the_review_window_closes_two_weeks_after_check_out(listing, client_for):
    stay = finished_stay(listing, days_since_check_out=15)

    response = post_review(client_for, stay)

    assert response.status_code == 400
    assert response.data["code"] == "review_window_closed"


@pytest.mark.parametrize("rating", [0, 6])
def test_rating_must_be_one_to_five(listing, client_for, rating):
    response = post_review(client_for, finished_stay(listing), rating=rating)

    assert response.status_code == 400
    assert "rating" in response.data["errors"]


def test_pending_reviews_list_open_stays_only(listing, client_for):
    guest = UserFactory()
    open_stay = finished_stay(listing, guest)
    finished_stay(listing, guest, days_since_check_out=20)
    post_review(client_for, finished_stay(listing, guest))
    finished_stay(listing)  # someone else's

    response = client_for(guest).get(reverse("reviews-pending"))

    assert response.status_code == 200
    assert [item["booking_id"] for item in response.data] == [str(open_stay.booking_id)]
    assert response.data[0]["listing"]["title"] == listing.title


def test_listing_reviews_are_public_and_paginated_by_cursor(listing, client_for, api_client):
    for rating in (3, 4, 5):
        post_review(client_for, finished_stay(listing), rating=rating)

    first = api_client.get(reverse("listing-reviews", args=[listing.pk]), {"page_size": 2})
    second = api_client.get(first.data["next"])

    assert first.status_code == 200
    assert [r["rating"] for r in first.data["results"]] == [5, 4]
    assert [r["rating"] for r in second.data["results"]] == [3]
    assert second.data["next"] is None


def test_reviews_of_unpublished_listings_are_hidden(api_client):
    draft = ListingFactory(status=ListingStatus.DRAFT)

    response = api_client.get(reverse("listing-reviews", args=[draft.pk]))

    assert response.status_code == 404


def test_host_replies_once(listing, client_for, api_client):
    post_review(client_for, finished_stay(listing))
    review = Review.objects.get()
    url = reverse("host-review-reply", args=[review.pk])

    response = client_for(listing.host).post(url, {"text": "Thank you, come back!"})
    again = client_for(listing.host).post(url, {"text": "Edited"})

    assert response.status_code == 200
    assert response.data["host_reply"] == "Thank you, come back!"
    assert response.data["host_replied_at"] is not None
    assert again.status_code == 409
    public = api_client.get(reverse("listing-reviews", args=[listing.pk]))
    assert public.data["results"][0]["host_reply"] == "Thank you, come back!"


def test_hosts_cannot_reply_to_reviews_of_other_listings(listing, client_for):
    post_review(client_for, finished_stay(listing))
    review = Review.objects.get()

    response = client_for(HostFactory()).post(
        reverse("host-review-reply", args=[review.pk]), {"text": "Hi"}
    )

    assert response.status_code == 404
