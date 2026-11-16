"""Public signing key exposure as a JWKS document (RFC 7517) with RFC 7638 key ids."""

import base64
import hashlib
import json
from functools import cache
from typing import Any

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from django.conf import settings
from jwt.algorithms import RSAAlgorithm


def _thumbprint(jwk: dict[str, Any]) -> str:
    canonical = json.dumps({"e": jwk["e"], "kty": jwk["kty"], "n": jwk["n"]}, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


@cache
def public_jwk() -> dict[str, Any]:
    public_key = load_pem_public_key(settings.SIMPLE_JWT["VERIFYING_KEY"].encode())
    if not isinstance(public_key, RSAPublicKey):
        raise TypeError("JWT verifying key must be an RSA public key.")
    jwk: dict[str, Any] = RSAAlgorithm.to_jwk(public_key, as_dict=True)
    jwk.update(kid=_thumbprint(jwk), use="sig", alg=settings.SIMPLE_JWT["ALGORITHM"])
    return jwk


def current_key_id() -> str:
    return str(public_jwk()["kid"])


def jwks() -> dict[str, list[dict[str, Any]]]:
    return {"keys": [public_jwk()]}
