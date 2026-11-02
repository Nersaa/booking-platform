import pytest
from contracts import ListingEvent, ListingEventType
from django.conf import settings
from django.db import transaction

from apps.listings import services
from apps.listings.models import Amenity, ListingStatus, PhotoStatus
from apps.outbox.models import OutboxEvent
from apps.outbox.services import outbox_add
from tests.factories import ListingFactory, PhotoFactory, make_image

pytestmark = pytest.mark.django_db


def events() -> list[ListingEvent]:
    return [
        ListingEvent.model_validate(e.payload) for e in OutboxEvent.objects.order_by("created_at")
    ]


@pytest.fixture
def pending_listing():
    listing = ListingFactory(status=ListingStatus.PENDING_REVIEW)
    PhotoFactory(listing=listing, position=1)
    listing.amenities.set(Amenity.objects.filter(code__in=["wifi", "kitchen"]))
    return listing


def test_publishing_emits_a_full_snapshot(pending_listing):
    services.listing_publish(listing=pending_listing)

    [event] = events()
    assert event.event_type is ListingEventType.PUBLISHED
    snapshot = event.listing
    assert snapshot.id == pending_listing.id
    assert snapshot.host_id == pending_listing.host_id
    assert snapshot.version == pending_listing.version + 1
    assert snapshot.is_listed is True
    assert snapshot.amenities == ("kitchen", "wifi")
    assert snapshot.cover_photo_url is not None
    assert snapshot.cover_photo_url.endswith("/thumb.webp")
    assert OutboxEvent.objects.get().routing_key == "listing.published"


def test_editing_a_published_listing_emits_update(pending_listing):
    listing = services.listing_publish(listing=pending_listing)

    services.listing_update(listing=listing, title="Renovated loft")

    published, updated = events()
    assert updated.event_type is ListingEventType.UPDATED
    assert updated.listing.title == "Renovated loft"
    assert updated.listing.version == published.listing.version + 1


def test_changes_invisible_to_other_services_emit_nothing():
    draft = ListingFactory()

    services.listing_update(listing=draft, title="Still a draft")
    services.listing_archive(listing=draft)

    assert not OutboxEvent.objects.exists()


def test_archiving_a_published_listing_unlists_it(pending_listing):
    listing = services.listing_publish(listing=pending_listing)

    services.listing_archive(listing=listing)

    archived = events()[-1]
    assert archived.event_type is ListingEventType.ARCHIVED
    assert archived.listing.is_listed is False


def test_photo_changes_of_a_published_listing_are_announced(pending_listing):
    listing = services.listing_publish(listing=pending_listing)
    extra = PhotoFactory(listing=listing, position=0)

    services.photo_delete(photo=extra)

    assert [e.event_type for e in events()] == [
        ListingEventType.PUBLISHED,
        ListingEventType.UPDATED,
    ]


def test_processed_photo_of_a_published_listing_is_announced(pending_listing, s3):
    listing = services.listing_publish(listing=pending_listing)
    photo = PhotoFactory(listing=listing, status=PhotoStatus.PROCESSING, position=5)
    s3.put_object(Bucket=settings.S3_BUCKET, Key=photo.original_key, Body=make_image())

    services.photo_process(photo_id=str(photo.pk))

    assert events()[-1].event_type is ListingEventType.UPDATED


def test_rolled_back_change_leaves_no_event(pending_listing):
    def publish_then_fail():
        with transaction.atomic():
            services.listing_publish(listing=pending_listing)
            raise RuntimeError("something later in the transaction failed")

    with pytest.raises(RuntimeError):
        publish_then_fail()

    assert not OutboxEvent.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_outbox_refuses_writes_outside_a_transaction():
    with pytest.raises(RuntimeError, match="inside the transaction"):
        outbox_add(event_id=ListingFactory.build().id, routing_key="x", payload={})
