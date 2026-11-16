"""Thin wrapper over the S3 API used for listing photos."""

import json
from functools import cache
from typing import TYPE_CHECKING, Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from django.conf import settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def _make_client(endpoint_url: str | None) -> "S3Client":
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


@cache
def internal_client() -> "S3Client":
    return _make_client(settings.S3_ENDPOINT_URL)


@cache
def public_client() -> "S3Client":
    return _make_client(settings.S3_PUBLIC_ENDPOINT_URL or settings.S3_ENDPOINT_URL)


def reset_clients() -> None:
    internal_client.cache_clear()
    public_client.cache_clear()


def ensure_bucket() -> None:
    """Create the bucket if needed and allow anonymous reads under `public/` only."""
    client = internal_client()
    bucket = settings.S3_BUCKET
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket}/public/*"],
            }
        ],
    }
    client.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))


def presigned_post(
    key: str, *, content_type: str, max_bytes: int, expires_in: int
) -> dict[str, Any]:
    return public_client().generate_presigned_post(
        Bucket=settings.S3_BUCKET,
        Key=key,
        Fields={"Content-Type": content_type},
        Conditions=[
            {"Content-Type": content_type},
            ["content-length-range", 1, max_bytes],
        ],
        ExpiresIn=expires_in,
    )


def object_size(key: str) -> int | None:
    try:
        head = internal_client().head_object(Bucket=settings.S3_BUCKET, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise
    return head["ContentLength"]


def download(key: str) -> bytes:
    obj = internal_client().get_object(Bucket=settings.S3_BUCKET, Key=key)
    return obj["Body"].read()


def upload(key: str, data: bytes, *, content_type: str) -> None:
    internal_client().put_object(
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type,
        CacheControl="public, max-age=31536000, immutable",
    )


def delete(keys: list[str]) -> None:
    if not keys:
        return
    internal_client().delete_objects(
        Bucket=settings.S3_BUCKET,
        Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
    )


def public_url(key: str) -> str:
    return f"{settings.MEDIA_PUBLIC_BASE_URL}/{key}"
