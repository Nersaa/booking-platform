"""Listing lifecycle and photo pipeline. All writes to listings go through here."""

from collections.abc import Iterable
from datetime import timedelta
from typing import Any

from contracts import ListingEventType
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.common import storage
from apps.common.exceptions import DomainError, InvalidStateTransitionError, PermissionDeniedError
from apps.listings import images
from apps.listings.events import emit_listing_event
from apps.listings.models import Amenity, Listing, ListingPhoto, ListingStatus, PhotoStatus
from apps.users.models import User

S = ListingStatus

TRANSITIONS: dict[str, set[str]] = {
    S.DRAFT: {S.PENDING_REVIEW, S.ARCHIVED},
    S.PENDING_REVIEW: {S.PUBLISHED, S.REJECTED, S.ARCHIVED},
    S.REJECTED: {S.PENDING_REVIEW, S.ARCHIVED},
    S.PUBLISHED: {S.ARCHIVED},
    S.ARCHIVED: set(),
}
EDITABLE_STATUSES = {S.DRAFT, S.REJECTED, S.PUBLISHED}

MAX_PHOTOS_PER_LISTING = 20
MAX_PHOTO_BYTES = 10 * 1024 * 1024
ALLOWED_PHOTO_TYPES = ("image/jpeg", "image/png", "image/webp")
UPLOAD_URL_TTL_SECONDS = 600
ABANDONED_UPLOAD_TTL = timedelta(hours=24)


def _lock(listing: Listing) -> Listing:
    return Listing.objects.select_for_update().get(pk=listing.pk)


def _transition(listing: Listing, target: str) -> None:
    if target not in TRANSITIONS[listing.status]:
        raise InvalidStateTransitionError(
            f"Cannot move listing from '{listing.status}' to '{target}'."
        )
    listing.status = target
    listing.version += 1


@transaction.atomic
def listing_create(*, host: User, amenities: Iterable[Amenity] = (), **fields: Any) -> Listing:
    if not host.is_host:
        raise PermissionDeniedError("Only hosts can create listings.")
    listing = Listing(host=host, **fields)
    listing.full_clean(exclude=["amenities"])
    listing.save()
    listing.amenities.set(amenities)
    return listing


@transaction.atomic
def listing_update(
    *, listing: Listing, amenities: Iterable[Amenity] | None = None, **fields: Any
) -> Listing:
    listing = _lock(listing)
    if listing.status not in EDITABLE_STATUSES:
        raise InvalidStateTransitionError(
            f"A listing in '{listing.status}' status cannot be edited."
        )
    for name, value in fields.items():
        setattr(listing, name, value)
    listing.version += 1
    listing.full_clean(exclude=["amenities"])
    listing.save()
    if amenities is not None:
        listing.amenities.set(amenities)
    if listing.status == S.PUBLISHED:
        emit_listing_event(listing, ListingEventType.UPDATED)
    return listing


@transaction.atomic
def listing_submit_for_review(*, listing: Listing) -> Listing:
    listing = _lock(listing)
    if not listing.photos.filter(status=PhotoStatus.READY).exists():
        raise DomainError("Add at least one processed photo before submitting for review.")
    _transition(listing, S.PENDING_REVIEW)
    listing.save(update_fields=["status", "version", "updated_at"])
    return listing


@transaction.atomic
def listing_publish(*, listing: Listing) -> Listing:
    listing = _lock(listing)
    _transition(listing, S.PUBLISHED)
    listing.rejection_reason = ""
    listing.published_at = timezone.now()
    listing.save(
        update_fields=["status", "version", "rejection_reason", "published_at", "updated_at"]
    )
    emit_listing_event(listing, ListingEventType.PUBLISHED)
    return listing


@transaction.atomic
def listing_reject(*, listing: Listing, reason: str) -> Listing:
    if not reason.strip():
        raise DomainError("A rejection reason is required.")
    listing = _lock(listing)
    _transition(listing, S.REJECTED)
    listing.rejection_reason = reason.strip()
    listing.save(update_fields=["status", "version", "rejection_reason", "updated_at"])
    return listing


@transaction.atomic
def listing_archive(*, listing: Listing) -> Listing:
    listing = _lock(listing)
    was_listed = listing.status == S.PUBLISHED
    _transition(listing, S.ARCHIVED)
    listing.save(update_fields=["status", "version", "updated_at"])
    # Other services only ever learned about published listings.
    if was_listed:
        emit_listing_event(listing, ListingEventType.ARCHIVED)
    return listing


@transaction.atomic
def listing_delete(*, listing: Listing) -> None:
    """Only drafts are deleted; anything that was ever reviewed is archived instead."""
    listing = _lock(listing)
    if listing.status != S.DRAFT:
        raise InvalidStateTransitionError("Only draft listings can be deleted; archive it instead.")
    keys = [key for photo in listing.photos.all() for key in photo.storage_keys]
    listing.delete()
    _delete_objects_on_commit(keys)


@transaction.atomic
def photo_request_upload(
    *, listing: Listing, content_type: str
) -> tuple[ListingPhoto, dict[str, Any]]:
    listing = _lock(listing)
    if listing.status not in EDITABLE_STATUSES:
        raise InvalidStateTransitionError(
            f"Photos of a '{listing.status}' listing cannot be changed."
        )
    if content_type not in ALLOWED_PHOTO_TYPES:
        raise DomainError(f"Unsupported content type. Allowed: {', '.join(ALLOWED_PHOTO_TYPES)}.")
    active = listing.photos.exclude(status=PhotoStatus.FAILED)
    if active.count() >= MAX_PHOTOS_PER_LISTING:
        raise DomainError(f"A listing can have at most {MAX_PHOTOS_PER_LISTING} photos.")

    last_position = active.aggregate(last=Max("position"))["last"]
    photo = ListingPhoto.objects.create(
        listing=listing,
        content_type=content_type,
        position=0 if last_position is None else last_position + 1,
    )
    upload = storage.presigned_post(
        photo.original_key,
        content_type=content_type,
        max_bytes=MAX_PHOTO_BYTES,
        expires_in=UPLOAD_URL_TTL_SECONDS,
    )
    return photo, upload


@transaction.atomic
def photo_confirm_upload(*, photo: ListingPhoto) -> ListingPhoto:
    from apps.listings.tasks import process_listing_photo

    photo = ListingPhoto.objects.select_for_update().get(pk=photo.pk)
    if photo.status != PhotoStatus.PENDING_UPLOAD:
        raise InvalidStateTransitionError(f"Photo is already '{photo.status}'.")
    if storage.object_size(photo.original_key) is None:
        raise DomainError("The file has not been uploaded yet.")

    photo.status = PhotoStatus.PROCESSING
    photo.save(update_fields=["status", "updated_at"])
    transaction.on_commit(lambda: process_listing_photo.delay(str(photo.pk)))
    return photo


@transaction.atomic
def photo_delete(*, photo: ListingPhoto) -> None:
    listing = _lock(photo.listing)
    if listing.status not in EDITABLE_STATUSES:
        raise InvalidStateTransitionError(
            f"Photos of a '{listing.status}' listing cannot be changed."
        )
    ready = listing.photos.filter(status=PhotoStatus.READY)
    if (
        listing.status == S.PUBLISHED
        and photo.status == PhotoStatus.READY
        and not ready.exclude(pk=photo.pk).exists()
    ):
        raise DomainError("A published listing must keep at least one photo.")
    keys = photo.storage_keys
    photo.delete()
    if listing.status == S.PUBLISHED:
        listing.version += 1
        listing.save(update_fields=["version", "updated_at"])
        emit_listing_event(listing, ListingEventType.UPDATED)
    _delete_objects_on_commit(keys)


def photo_process(*, photo_id: str) -> None:
    """Turn an uploaded original into public web variants. Safe to run more than once."""
    photo = ListingPhoto.objects.filter(pk=photo_id, status=PhotoStatus.PROCESSING).first()
    if photo is None:
        return

    try:
        variants = images.render_variants(storage.download(photo.original_key))
    except images.InvalidImageError:
        ListingPhoto.objects.filter(pk=photo.pk).update(
            status=PhotoStatus.FAILED, updated_at=timezone.now()
        )
        storage.delete([photo.original_key])
        return

    keys = {"large": photo.large_key, "thumb": photo.thumb_key}
    for variant in variants:
        storage.upload(keys[variant.name], variant.data, content_type="image/webp")
    large = next(v for v in variants if v.name == "large")

    with transaction.atomic():
        # Listing first, then photo: the same lock order as everywhere else.
        listing = Listing.objects.select_for_update().filter(pk=photo.listing_id).first()
        updated = ListingPhoto.objects.filter(pk=photo.pk, status=PhotoStatus.PROCESSING).update(
            status=PhotoStatus.READY,
            width=large.width,
            height=large.height,
            updated_at=timezone.now(),
        )
        if updated and listing is not None and listing.status == S.PUBLISHED:
            listing.version += 1
            listing.save(update_fields=["version", "updated_at"])
            emit_listing_event(listing, ListingEventType.UPDATED)
    storage.delete([photo.original_key])


def photos_cleanup_abandoned() -> int:
    """Remove uploads that were never confirmed and photos that failed processing."""
    cutoff = timezone.now() - ABANDONED_UPLOAD_TTL
    stale = list(
        ListingPhoto.objects.filter(
            status__in=(PhotoStatus.PENDING_UPLOAD, PhotoStatus.FAILED), updated_at__lt=cutoff
        )
    )
    storage.delete([key for photo in stale for key in photo.storage_keys])
    ListingPhoto.objects.filter(pk__in=[photo.pk for photo in stale]).delete()
    return len(stale)


def _delete_objects_on_commit(keys: list[str]) -> None:
    from apps.listings.tasks import delete_storage_objects

    if keys:
        transaction.on_commit(lambda: delete_storage_objects.delay(keys))
