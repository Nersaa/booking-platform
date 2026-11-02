"""Access tokens are issued by Catalog (RS256) and verified here against its JWKS.

Keys are fetched once and cached; an unknown `kid` triggers a refresh, which is how a
rotated key is picked up without a restart.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Annotated, Any, Protocol
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.errors import NotAuthenticatedError, PermissionDeniedError, ServiceUnavailableError

logger = logging.getLogger(__name__)

ALGORITHMS = ["RS256"]
# Do not hammer Catalog when someone sends tokens with made-up key ids.
MIN_REFRESH_INTERVAL_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    roles: frozenset[str]

    @property
    def is_host(self) -> bool:
        return "host" in self.roles


class KeyStore(Protocol):
    async def get(self, kid: str) -> jwt.PyJWK | None: ...


class JWKSKeyStore:
    def __init__(self, url: str, client: httpx.AsyncClient, max_age_seconds: float) -> None:
        self._url = url
        self._client = client
        self._max_age = max_age_seconds
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at = float("-inf")
        self._attempted_at = float("-inf")
        self._lock = asyncio.Lock()

    async def get(self, kid: str) -> jwt.PyJWK | None:
        if self._needs_refresh(kid):
            async with self._lock:
                if self._needs_refresh(kid):  # another request may have refreshed meanwhile
                    await self._refresh()
        if not self._keys:
            raise ServiceUnavailableError("Token verification is temporarily unavailable.")
        return self._keys.get(kid)

    def _needs_refresh(self, kid: str) -> bool:
        now = time.monotonic()
        if now - self._attempted_at < MIN_REFRESH_INTERVAL_SECONDS:
            return False
        return kid not in self._keys or now - self._fetched_at > self._max_age

    async def _refresh(self) -> None:
        self._attempted_at = time.monotonic()
        try:
            response = await self._client.get(self._url, timeout=5.0)
            response.raise_for_status()
            key_set = jwt.PyJWKSet.from_dict(response.json())
        except (httpx.HTTPError, ValueError, jwt.PyJWTError) as exc:
            # Keep serving the cached keys: Catalog being down must not break Booking.
            logger.warning("Could not refresh JWKS from %s: %s", self._url, exc)
            return
        self._keys = {key.key_id: key for key in key_set.keys if key.key_id}
        self._fetched_at = self._attempted_at


class TokenVerifier:
    def __init__(self, keys: KeyStore, *, issuer: str, audience: str) -> None:
        self._keys = keys
        self._issuer = issuer
        self._audience = audience

    async def verify(self, token: str) -> Principal:
        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except jwt.InvalidTokenError as exc:
            raise NotAuthenticatedError("Malformed token.") from exc
        key = await self._keys.get(kid) if isinstance(kid, str) else None
        if key is None:
            raise NotAuthenticatedError("Token is signed with an unknown key.")

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
