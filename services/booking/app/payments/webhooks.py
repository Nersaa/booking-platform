"""Authenticity of provider webhooks: HMAC-SHA256 over "<timestamp>.<raw body>".

Header format: `Webhook-Signature: t=<unix seconds>,v1=<hex digest>`. The timestamp is
part of the signed data and must be recent, which stops replays of captured requests.
"""

import hashlib
import hmac
import time
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel

from app.errors import DomainError

SIGNATURE_HEADER = "Webhook-Signature"
TOLERANCE_SECONDS = 300


class InvalidSignatureError(DomainError):
    status_code = 400
    code = "invalid_signature"


def sign(secret: str, body: bytes, timestamp: int) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"t={timestamp},v1={digest.hexdigest()}"


def verify(secret: str, body: bytes, header: str | None, now: float | None = None) -> None:
    if not header:
        raise InvalidSignatureError("Missing webhook signature.")
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        timestamp = int(parts["t"])
        received = parts["v1"]
    except (KeyError, ValueError) as exc:
        raise InvalidSignatureError("Malformed webhook signature.") from exc

    if abs((now if now is not None else time.time()) - timestamp) > TOLERANCE_SECONDS:
        raise InvalidSignatureError("Webhook timestamp is outside the tolerance window.")
    expected = sign(secret, body, timestamp).split("v1=", 1)[1]
    if not hmac.compare_digest(expected, received):
        raise InvalidSignatureError("Webhook signature does not match.")


class WebhookType(StrEnum):
    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_FAILED = "payment.failed"
    REFUND_SUCCEEDED = "refund.succeeded"
    REFUND_FAILED = "refund.failed"


class WebhookObject(BaseModel):
    id: str
    reference: UUID  # our Payment or Refund id
    amount: int


class WebhookEvent(BaseModel):
    id: str
    type: WebhookType
    data: WebhookObject
