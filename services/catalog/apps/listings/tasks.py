from botocore.exceptions import BotoCoreError, ClientError
from celery import shared_task

from apps.common import storage
from apps.listings import services

STORAGE_ERRORS = (BotoCoreError, ClientError)


@shared_task(autoretry_for=STORAGE_ERRORS, retry_backoff=True, max_retries=5)
def process_listing_photo(photo_id: str) -> None:
    services.photo_process(photo_id=photo_id)


@shared_task(autoretry_for=STORAGE_ERRORS, retry_backoff=True, max_retries=5)
def delete_storage_objects(keys: list[str]) -> None:
    storage.delete(keys)


@shared_task
def cleanup_abandoned_photos() -> int:
    return services.photos_cleanup_abandoned()
