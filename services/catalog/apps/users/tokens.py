"""simplejwt tokens that carry a `kid` header so other services can pick the key from JWKS."""

from typing import Any, cast

import jwt
from rest_framework_simplejwt import tokens
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.settings import api_settings

from apps.users.keys import current_key_id
from apps.users.models import User


class KeyIdTokenBackend(TokenBackend):
    def encode(self, payload: dict[str, Any]) -> str:
        claims = payload.copy()
        if self.audience is not None:
            claims["aud"] = self.audience
        if self.issuer is not None:
            claims["iss"] = self.issuer
        return jwt.encode(
            claims,
            self.prepared_signing_key,
            algorithm=self.algorithm,
            headers={"kid": current_key_id()},
            json_encoder=self.json_encoder,
        )


token_backend = KeyIdTokenBackend(
    api_settings.ALGORITHM,
    api_settings.SIGNING_KEY,
    api_settings.VERIFYING_KEY,
    api_settings.AUDIENCE,
    api_settings.ISSUER,
    api_settings.JWK_URL,
    api_settings.LEEWAY,
    api_settings.JSON_ENCODER,
)


class AccessToken(tokens.AccessToken):
    _token_backend = token_backend


class RefreshToken(tokens.RefreshToken):
    _token_backend = token_backend
    access_token_class = AccessToken

    @classmethod
    def for_user(cls, user: User) -> "RefreshToken":  # type: ignore[override]
        token = cast("RefreshToken", super().for_user(user))
        token["roles"] = user.roles
        return token


def issue_token_pair(user: User) -> dict[str, str]:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}
