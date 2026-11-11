import json
from io import StringIO

import pytest
from django.core.management import call_command

from apps.listings.models import Listing, ListingStatus
from apps.outbox.models import OutboxEvent

pytestmark = pytest.mark.django_db


def test_seed_publishes_listings_through_the_outbox():
    out = StringIO()

    call_command("seed_listings", count=5, stdout=out)

    result = json.loads(out.getvalue())
    assert len(result["listing_ids"]) == 5
    assert result["host_token"]
    assert Listing.objects.filter(status=ListingStatus.PUBLISHED).count() == 5
    assert OutboxEvent.objects.filter(routing_key="listing.published").count() == 5
