from django.db.models import Prefetch, QuerySet

from apps.listings.models import Listing, ListingPhoto, ListingStatus, PhotoStatus
from apps.users.models import User


def host_listings(*, host: User) -> QuerySet[Listing]:
    return (
        Listing.objects.filter(host=host)
        .exclude(status=ListingStatus.ARCHIVED)
        .prefetch_related("amenities", "photos")
    )


def published_listings() -> QuerySet[Listing]:
    ready_photos = ListingPhoto.objects.filter(status=PhotoStatus.READY)
    return (
        Listing.objects.filter(status=ListingStatus.PUBLISHED)
        .select_related("host")
        .prefetch_related("amenities", Prefetch("photos", queryset=ready_photos))
    )
