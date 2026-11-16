import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key")
os.environ.setdefault("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/catalog")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from config.settings import *  # noqa: F403
from config.settings import REST_FRAMEWORK, SIMPLE_JWT

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
SIMPLE_JWT["SIGNING_KEY"] = _private_key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
SIMPLE_JWT["VERIFYING_KEY"] = (
    _private_key.public_key()
    .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    .decode()
)

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {"auth": "1000/min"}
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

S3_ENDPOINT_URL = None
S3_PUBLIC_ENDPOINT_URL = None
S3_ACCESS_KEY = "test"
S3_SECRET_KEY = "test"  # noqa: S105 - moto accepts any credentials
S3_BUCKET = "test-photos"
MEDIA_PUBLIC_BASE_URL = "http://testserver/media"

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]  # noqa: F405
