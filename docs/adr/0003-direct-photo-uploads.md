# 3. Direct-to-storage photo uploads with async processing

Status: accepted

## Context

Photos are the largest payloads in the system. Streaming them through the API
workers ties up processes and memory, and user-supplied images may carry GPS data
in EXIF or be crafted to exhaust memory when decoded.

## Decision

- The API issues a presigned POST that pins the object key, content type and a
  10 MB size limit. The client uploads straight to S3-compatible storage.
- The client confirms the upload; a Celery task validates the image (pixel limit,
  minimum size), renders WebP variants and drops all metadata.
- Originals live under a private `uploads/` prefix and are deleted after processing.
  Only `public/` is readable anonymously, served through the gateway at `/media/`.
- A periodic task removes uploads that were never confirmed.
- Storage is S3-compatible: RustFS locally (MinIO no longer publishes images), any S3
  provider in production. Bucket and policy are created by `manage.py ensure_storage`.

## Consequences

- API workers never handle file bytes.
- Photos appear with a short delay (`processing` → `ready`).
