import pytest
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.urls import reverse

from apps.common.exceptions import DomainError, InvalidStateTransitionError
from apps.listings import services
from apps.listings.models import ListingStatus
from tests.factories import ListingFactory, UserFactory

pytestmark = pytest.mark.django_db

CHANGELIST_URL = reverse("admin:listings_listing_changelist")


@pytest.fixture
def moderator_client(client):
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    return client


def test_publish_moves_pending_listing_live():
    listing = ListingFactory(status=ListingStatus.PENDING_REVIEW, rejection_reason="old")

    published = services.listing_publish(listing=listing)

    assert published.status == ListingStatus.PUBLISHED
    assert published.published_at is not None
    assert published.rejection_reason == ""


def test_draft_cannot_be_published_directly():
    with pytest.raises(InvalidStateTransitionError):
        services.listing_publish(listing=ListingFactory())


def test_reject_requires_reason():
    with pytest.raises(DomainError):
        services.listing_reject(
            listing=ListingFactory(status=ListingStatus.PENDING_REVIEW), reason="  "
        )


def test_rejected_listing_can_be_fixed_and_resubmitted(client_for):
    listing = ListingFactory(status=ListingStatus.PENDING_REVIEW)
    services.listing_reject(listing=listing, reason="Photos are blurry")
    client = client_for(listing.host)

    detail = client.get(reverse("host-listings-detail", args=[listing.pk]))
    edit = client.patch(reverse("host-listings-detail", args=[listing.pk]), {"title": "Fixed"})

    assert detail.data["status"] == ListingStatus.REJECTED
    assert detail.data["rejection_reason"] == "Photos are blurry"
    assert edit.status_code == 200


def test_admin_publish_action(moderator_client):
    listing = ListingFactory(status=ListingStatus.PENDING_REVIEW)

    moderator_client.post(
        CHANGELIST_URL, {"action": "publish_listings", ACTION_CHECKBOX_NAME: [listing.pk]}
    )

    listing.refresh_from_db()
    assert listing.status == ListingStatus.PUBLISHED


def test_admin_reject_action_asks_for_reason_then_applies_it(moderator_client):
    listing = ListingFactory(status=ListingStatus.PENDING_REVIEW)
    data = {"action": "reject_listings", ACTION_CHECKBOX_NAME: [listing.pk]}

    form_page = moderator_client.post(CHANGELIST_URL, data)
    moderator_client.post(CHANGELIST_URL, data | {"apply": "1", "reason": "Wrong address"})

    listing.refresh_from_db()
    assert form_page.status_code == 200
    assert b'name="reason"' in form_page.content
    assert listing.status == ListingStatus.REJECTED
    assert listing.rejection_reason == "Wrong address"


def test_admin_action_reports_invalid_transitions(moderator_client):
    listing = ListingFactory(status=ListingStatus.DRAFT)

    response = moderator_client.post(
        CHANGELIST_URL,
        {"action": "publish_listings", ACTION_CHECKBOX_NAME: [listing.pk]},
        follow=True,
    )

    listing.refresh_from_db()
    assert listing.status == ListingStatus.DRAFT
    assert b"Cannot move listing" in response.content
