import io
from datetime import timedelta

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.listings import services
from apps.listings.models import ListingPhoto, ListingStatus, PhotoStatus
from tests.factories import ListingFactory, PhotoFactory, make_image

pytestmark = pytest.mark.django_db


def photos_url(listing):
    return reverse("host-listing-photos", args=[listing.pk])


def complete_url(photo):
    return reverse("host-listing-photo-complete", args=[photo.listing_id, photo.pk])


def keys_in_bucket(s3) -> set[str]:
    return {obj["Key"] for obj in s3.list_objects_v2(Bucket=settings.S3_BUCKET).get("Contents", [])}


def start_upload(client, listing) -> ListingPhoto:
    response = client.post(photos_url(listing), {"content_type": "image/jpeg"})
    assert response.status_code == 201, response.data
    return ListingPhoto.objects.get(pk=response.data["photo"]["id"])


def test_upload_request_returns_presigned_post(client_for):
    listing = ListingFactory()

    response = client_for(listing.host).post(photos_url(listing), {"content_type": "image/png"})

    photo = ListingPhoto.objects.get(pk=response.data["photo"]["id"])
    upload = response.data["upload"]
    assert response.status_code == 201
    assert photo.status == PhotoStatus.PENDING_UPLOAD
    assert upload["fields"]["key"] == photo.original_key
    assert upload["fields"]["Content-Type"] == "image/png"
    assert "policy" in upload["fields"]


def test_upload_request_rejects_unsupported_type(client_for):
    listing = ListingFactory()

    response = client_for(listing.host).post(photos_url(listing), {"content_type": "image/gif"})

    assert response.status_code == 400


def test_foreign_listing_photos_are_not_accessible(client_for):
    listing = ListingFactory()

    response = client_for(ListingFactory().host).post(
        photos_url(listing), {"content_type": "image/jpeg"}
    )

    assert response.status_code == 404


def test_complete_before_upload_fails(client_for):
    listing = ListingFactory()
    client = client_for(listing.host)
    photo = start_upload(client, listing)

    response = client.post(complete_url(photo))

    assert response.status_code == 400
    assert "not been uploaded" in response.json()["detail"]


def test_uploaded_photo_is_processed_into_public_variants(
    client_for, s3, django_capture_on_commit_callbacks
):
    listing = ListingFactory()
    client = client_for(listing.host)
    photo = start_upload(client, listing)
    s3.put_object(Bucket=settings.S3_BUCKET, Key=photo.original_key, Body=make_image((2400, 1800)))

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(complete_url(photo))

    photo.refresh_from_db()
    assert response.status_code == 202
    assert photo.status == PhotoStatus.READY
    assert (photo.width, photo.height) == (1600, 1200)
    assert keys_in_bucket(s3) == {photo.large_key, photo.thumb_key}
    large = s3.get_object(Bucket=settings.S3_BUCKET, Key=photo.large_key)["Body"].read()
    assert not Image.open(io.BytesIO(large)).getexif()


@pytest.mark.parametrize("payload", [b"not an image", make_image((300, 300))])
def test_invalid_upload_is_marked_failed_and_removed(
    client_for, s3, django_capture_on_commit_callbacks, payload
):
    listing = ListingFactory()
    client = client_for(listing.host)
    photo = start_upload(client, listing)
    s3.put_object(Bucket=settings.S3_BUCKET, Key=photo.original_key, Body=payload)

    with django_capture_on_commit_callbacks(execute=True):
        client.post(complete_url(photo))

    photo.refresh_from_db()
    assert photo.status == PhotoStatus.FAILED
    assert keys_in_bucket(s3) == set()


def test_published_listing_keeps_its_last_photo(client_for):
    listing = ListingFactory(status=ListingStatus.PUBLISHED)
    photo = PhotoFactory(listing=listing)

    response = client_for(listing.host).delete(
        reverse("host-listing-photo", args=[listing.pk, photo.pk])
    )

    assert response.status_code == 400
    assert ListingPhoto.objects.filter(pk=photo.pk).exists()


def test_cleanup_removes_abandoned_uploads(s3):
    stale = PhotoFactory(status=PhotoStatus.PENDING_UPLOAD)
    fresh = PhotoFactory(status=PhotoStatus.PENDING_UPLOAD)
    ListingPhoto.objects.filter(pk=stale.pk).update(updated_at=timezone.now() - timedelta(days=2))
    s3.put_object(Bucket=settings.S3_BUCKET, Key=stale.original_key, Body=b"x")

    removed = services.photos_cleanup_abandoned()

    assert removed == 1
    assert list(ListingPhoto.objects.all()) == [fresh]
    assert keys_in_bucket(s3) == set()
