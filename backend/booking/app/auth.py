"""Access tokens are issued by Catalog (RS256) and verified here with its public keys.

The keys come from Catalog's JWKS endpoint. PyJWKClient caches them and fetches them
again when a token names an unknown key id, which is how a rotated key is picked up
without a restart.
"""

from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

from app.errors import NotAuthenticatedError, PermissionDeniedError, ServiceUnavailableError

ALGORITHMS = ["RS256"]


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    roles: frozenset[str]

    @property
    def is_host(self) -> bool:
        return "host" in self.roles


class TokenVerifier:
    def __init__(self, jwks: jwt.PyJWKClient, *, issuer: str, audience: str) -> None:
        self._jwks = jwks
        self._issuer = issuer
        self._audience = audience

    async def verify(self, token: str) -> Principal:
        try:
            # PyJWKClient does blocking HTTP, but only when its cache misses.
            key = await run_in_threadpool(self._jwks.get_signing_key_from_jwt, token)
        except jwt.PyJWKClientConnectionError as exc:
            raise ServiceUnavailableError("Token verification is temporarily unavailable.") from exc
        except jwt.PyJWKClientError as exc:
            raise NotAuthenticatedError("Token is signed with an unknown key.") from exc
        except jwt.DecodeError as exc:
            raise NotAuthenticatedError("Malformed token.") from exc

        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key,
                algorithms=ALGORITHMS,
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise NotAuthenticatedError("Token has expired.") from exc
        except jwt.InvalidTokenError as exc:
            raise NotAuthenticatedError("Token is invalid.") from exc

        if claims.get("token_type") != "access":
            raise NotAuthenticatedError("An access token is required.")
        try:
            user_id = UUID(claims["sub"])
        except ValueError as exc:
            raise NotAuthenticatedError("Token is invalid.") from exc
        return Principal(user_id=user_id, roles=frozenset(claims.get("roles", ())))


_bearer = HTTPBearer(auto_error=False)


async def current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None:
        raise NotAuthenticatedError("Authentication credentials were not provided.")
    verifier: TokenVerifier = request.app.state.verifier
    return await verifier.verify(credentials.credentials)


async def current_host(principal: Annotated[Principal, Depends(current_principal)]) -> Principal:
    if not principal.is_host:
        raise PermissionDeniedError("Only hosts can manage listings.")
    return principal


HostDep = Annotated[Principal, Depends(current_host)]
