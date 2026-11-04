"""Reviews: only real guests, once per stay, within two weeks of check-out."""

from datetime import timedelta

from contracts import BookingSnapshot
from django.db import transaction
from django.utils import timezone
from rest_framework import status

from apps.common.exceptions import DomainError
from apps.listings.models import Listing
from apps.listings.services import listing_add_review_score
from apps.reviews.models import Review, ReviewableStay
from apps.users.models import User

REVIEW_WINDOW = timedelta(days=14)


class ReviewWindowClosedError(DomainError):
    code = "review_window_closed"


class AlreadyReviewedError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    code = "already_reviewed"


class AlreadyRepliedError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    code = "already_replied"


def stay_record(booking: BookingSnapshot) -> ReviewableStay | None:
    """Opens the review window for a finished stay. Idempotent per booking."""
    if not (
        Listing.objects.filter(pk=booking.listing_id).exists()
        and User.objects.filter(pk=booking.guest_id).exists()
    ):
        return None
    stay, _ = ReviewableStay.objects.get_or_create(
        booking_id=booking.id,
        defaults={
            "listing_id": booking.listing_id,
            "guest_id": booking.guest_id,
            "check_in": booking.check_in,
            "check_out": booking.check_out,
            "review_deadline": booking.check_out + REVIEW_WINDOW,
        },
    )
    return stay


@transaction.atomic
def review_create(*, stay: ReviewableStay, rating: int, text: str) -> Review:
    stay = ReviewableStay.objects.select_for_update().get(pk=stay.pk)
    if Review.objects.filter(stay=stay).exists():
        raise AlreadyReviewedError("This stay has already been reviewed.")
    if timezone.localdate() > stay.review_deadline:
        raise ReviewWindowClosedError("Reviews can be left up to 14 days after check-out.")
    review = Review(
        stay=stay, listing_id=stay.listing_id, author_id=stay.guest_id, rating=rating, text=text
    )
    review.full_clean()
    review.save()
    listing_add_review_score(listing_id=stay.listing_id, rating=rating)
    return review


@transaction.atomic
def review_reply(*, review: Review, text: str) -> Review:
    review = Review.objects.select_for_update().get(pk=review.pk)
    if review.host_reply:
        raise AlreadyRepliedError("This review already has a reply.")
    review.host_reply = text
    review.host_replied_at = timezone.now()
    review.save(update_fields=["host_reply", "host_replied_at", "updated_at"])
    return review
