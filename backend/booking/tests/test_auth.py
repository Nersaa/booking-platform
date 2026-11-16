from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth import TokenVerifier
from app.errors import NotAuthenticatedError, ServiceUnavailableError
from tests.conftest import StaticJWKS, TokenFactory, public_jwk

PRICING_URL = "/api/v1/host/listings/{}/pricing"


async def test_missing_token_is_rejected_with_problem_details(client: httpx.AsyncClient) -> None:
    response = await client.get(PRICING_URL.format(uuid4()))

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["code"] == "not_authenticated"


@pytest.mark.parametrize(
    ("token_kwargs", "detail"),
    [
        ({"expires_in": -10}, "Token has expired."),
        ({"token_type": "refresh"}, "An access token is required."),
        ({"aud": "someone-else"}, "Token is invalid."),
        ({"iss": "attacker"}, "Token is invalid."),
        ({"kid": "unknown"}, "Token is signed with an unknown key."),
    ],
)
async def test_invalid_tokens_are_rejected(
    client: httpx.AsyncClient, make_token: TokenFactory, token_kwargs: dict[str, Any], detail: str
) -> None:
    token = make_token(roles=("guest", "host"), **token_kwargs)

    response = await client.get(
        PRICING_URL.format(uuid4()), headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == detail


async def test_token_signed_by_another_key_is_rejected(
    client: httpx.AsyncClient, make_token: TokenFactory
) -> None:
    forged = make_token(roles=("host",), key=rsa.generate_private_key(65537, 2048))

    response = await client.get(
        PRICING_URL.format(uuid4()), headers={"Authorization": f"Bearer {forged}"}
    )

    assert response.status_code == 401


async def test_host_endpoints_require_host_role(
    client: httpx.AsyncClient, auth: Callable[..., dict[str, str]]
) -> None:
    response = await client.get(PRICING_URL.format(uuid4()), headers=auth(uuid4(), "guest"))

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


async def test_verifier_returns_principal(
    verifier: TokenVerifier, make_token: TokenFactory
) -> None:
    user_id = uuid4()

    principal = await verifier.verify(make_token(user_id, ("guest", "host")))

    assert principal.user_id == user_id
    assert principal.is_host


async def test_keys_are_fetched_once_and_cached(
    verifier: TokenVerifier, jwks: StaticJWKS, make_token: TokenFactory
) -> None:
    for _ in range(3):
        await verifier.verify(make_token())

    assert jwks.calls == 1


async def test_rotated_key_is_picked_up_without_restart(
    verifier: TokenVerifier, jwks: StaticJWKS, make_token: TokenFactory
) -> None:
    await verifier.verify(make_token())

    new_key = rsa.generate_private_key(65537, 2048)
    jwks.keys.append(public_jwk(new_key, kid="rotated"))
    principal = await verifier.verify(make_token(key=new_key, kid="rotated"))

    assert isinstance(principal.user_id, UUID)
    assert jwks.calls == 2


async def test_catalog_down_without_cached_keys_means_service_unavailable(
    verifier: TokenVerifier, jwks: StaticJWKS, make_token: TokenFactory
) -> None:
    jwks.down = True

    with pytest.raises(ServiceUnavailableError):
        await verifier.verify(make_token())


async def test_malformed_token(verifier: TokenVerifier) -> None:
    with pytest.raises(NotAuthenticatedError, match="Malformed"):
        await verifier.verify("not-a-jwt")
