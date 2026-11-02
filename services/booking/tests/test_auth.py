from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import auth
from app.auth import JWKSKeyStore, TokenVerifier
from app.errors import NotAuthenticatedError, ServiceUnavailableError
from tests.conftest import AUDIENCE, ISSUER, KEY_ID, TokenFactory, public_jwk

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


class FakeJWKSEndpoint:
    def __init__(self, keys: list[dict[str, Any]]) -> None:
        self.keys = keys
        self.calls = 0
        self.fail = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.fail:
            return httpx.Response(503)
        return httpx.Response(200, json={"keys": self.keys})


@pytest.fixture
def jwks_endpoint(signing_key: rsa.RSAPrivateKey) -> FakeJWKSEndpoint:
    return FakeJWKSEndpoint([public_jwk(signing_key)])


@pytest.fixture
def key_store(jwks_endpoint: FakeJWKSEndpoint) -> JWKSKeyStore:
    http = httpx.AsyncClient(transport=httpx.MockTransport(jwks_endpoint))
    return JWKSKeyStore("http://catalog/.well-known/jwks.json", http, max_age_seconds=3600)


async def test_jwks_is_fetched_once_and_cached(
    key_store: JWKSKeyStore, jwks_endpoint: FakeJWKSEndpoint, make_token: TokenFactory
) -> None:
    verifier = TokenVerifier(key_store, issuer=ISSUER, audience=AUDIENCE)

    for _ in range(3):
        await verifier.verify(make_token())

    assert jwks_endpoint.calls == 1


async def test_unknown_key_id_triggers_refresh_to_pick_up_rotated_key(
    key_store: JWKSKeyStore,
    jwks_endpoint: FakeJWKSEndpoint,
    make_token: TokenFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "MIN_REFRESH_INTERVAL_SECONDS", 0)
    verifier = TokenVerifier(key_store, issuer=ISSUER, audience=AUDIENCE)
    await verifier.verify(make_token())

    new_key = rsa.generate_private_key(65537, 2048)
    jwks_endpoint.keys.append(public_jwk(new_key, kid="rotated"))
    principal = await verifier.verify(make_token(key=new_key, kid="rotated"))

    assert isinstance(principal.user_id, UUID)
    assert jwks_endpoint.calls == 2


async def test_unknown_key_ids_do_not_hammer_catalog(
    key_store: JWKSKeyStore, jwks_endpoint: FakeJWKSEndpoint
) -> None:
    await key_store.get(KEY_ID)
    for _ in range(5):
        assert await key_store.get("made-up") is None

    assert jwks_endpoint.calls == 1


async def test_cached_keys_survive_catalog_outage(
    key_store: JWKSKeyStore, jwks_endpoint: FakeJWKSEndpoint, monkeypatch: pytest.MonkeyPatch
) -> None:
    await key_store.get(KEY_ID)
    jwks_endpoint.fail = True
    monkeypatch.setattr(auth, "MIN_REFRESH_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(key_store, "_max_age", 0)

    assert await key_store.get(KEY_ID) is not None
    assert jwks_endpoint.calls == 2


async def test_no_keys_at_all_means_service_unavailable(
    key_store: JWKSKeyStore, jwks_endpoint: FakeJWKSEndpoint
) -> None:
    jwks_endpoint.fail = True

    with pytest.raises(ServiceUnavailableError):
        await key_store.get(KEY_ID)


async def test_malformed_token(verifier: TokenVerifier) -> None:
    with pytest.raises(NotAuthenticatedError, match="Malformed"):
        await verifier.verify("not-a-jwt")
