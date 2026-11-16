import json

from django.conf import settings
from django.core.management import call_command


def test_ensure_storage_is_idempotent_and_exposes_only_public_prefix(s3):
    s3.delete_bucket(Bucket=settings.S3_BUCKET)

    call_command("ensure_storage")
    call_command("ensure_storage")

    policy = json.loads(s3.get_bucket_policy(Bucket=settings.S3_BUCKET)["Policy"])
    assert policy["Statement"][0]["Resource"] == [f"arn:aws:s3:::{settings.S3_BUCKET}/public/*"]
    assert policy["Statement"][0]["Action"] == ["s3:GetObject"]
