import json
from io import StringIO

import pytest
from django.conf import settings
from django.core.management import call_command

from apps.listings.models import Listing, ListingStatus, PhotoStatus
from apps.outbox.models import OutboxEvent
from tests.factories import ListingFactory

pytestmark = pytest.mark.django_db


def test_seed_publishes_listings_with_photos_through_the_outbox(s3):
    out = StringIO()

    call_command("seed_listings", count=3, stdout=out)

    result = json.loads(out.getvalue())
    assert len(result["listing_ids"]) == 3
    assert result["host_token"]
    for listing in Listing.objects.filter(status=ListingStatus.PUBLISHED):
        photos = listing.photos.filter(status=PhotoStatus.READY).order_by("position")
        assert 3 <= photos.count() <= 5
        first = photos.first()
        s3.head_object(Bucket=settings.S3_BUCKET, Key=first.thumb_key)  # the file exists
    events = OutboxEvent.objects.filter(routing_key="listing.published")
    assert events.count() == 3
    assert all(e.payload["listing"]["cover_photo_url"] for e in events)


def test_seed_photos_fills_only_listings_without_photos():
    bare = ListingFactory(status=ListingStatus.PUBLISHED)
    out = StringIO()

    call_command("seed_photos", stdout=out)
    call_command("seed_photos", stdout=StringIO())  # running again changes nothing

    assert bare.photos.filter(status=PhotoStatus.READY).count() >= 3
    assert "Added photos to 1 listing(s)." in out.getvalue()
    [event] = OutboxEvent.objects.filter(routing_key="listing.updated")
    assert event.payload["listing"]["cover_photo_url"].endswith("/thumb.webp")
