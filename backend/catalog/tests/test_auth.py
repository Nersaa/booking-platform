import jwt
import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework.test import APIClient

from tests.factories import DEFAULT_PASSWORD, UserFactory

pytestmark = pytest.mark.django_db


def login(client: APIClient, email: str, password: str = DEFAULT_PASSWORD) -> dict[str, str]:
    response = client.post(reverse("auth-token"), {"email": email, "password": password})
    assert response.status_code == 200, response.data
    return response.data


def verify_with_jwks(client: APIClient, token: str) -> dict:
    """Validate a token the way another service would: only with the public JWKS."""
    jwks = client.get(reverse("jwks")).json()
    key_id = jwt.get_unverified_header(token)["kid"]
    jwk = next(key for key in jwks["keys"] if key["kid"] == key_id)
    return jwt.decode(
        token,
        key=jwt.PyJWK(jwk).key,
        algorithms=["RS256"],
        audience=settings.SIMPLE_JWT["AUDIENCE"],
        issuer=settings.SIMPLE_JWT["ISSUER"],
    )


def test_register_normalises_email_and_hides_password(api_client):
    response = api_client.post(
        reverse("auth-register"),
        {"email": "  Guest@Example.COM ", "password": DEFAULT_PASSWORD, "first_name": "Ann"},
    )

    assert response.status_code == 201
    assert response.data["email"] == "guest@example.com"
    assert "password" not in response.data
    assert response.data["is_host"] is False


def test_register_rejects_duplicate_email_case_insensitively(api_client):
    UserFactory(email="taken@example.com")

    response = api_client.post(
        reverse("auth-register"),
        {"email": "TAKEN@example.com", "password": DEFAULT_PASSWORD, "first_name": "Ann"},
    )

    assert response.status_code == 400
    assert response["Content-Type"] == "application/problem+json"
    assert "email" in response.json()["errors"]


def test_register_rejects_weak_password(api_client):
    response = api_client.post(
        reverse("auth-register"),
        {"email": "new@example.com", "password": "12345678", "first_name": "Ann"},
    )

    assert response.status_code == 400


def test_login_issues_tokens_verifiable_through_jwks(api_client):
    user = UserFactory()

    tokens = login(api_client, user.email.upper())
    claims = verify_with_jwks(api_client, tokens["access"])

    assert claims["sub"] == str(user.id)
    assert claims["roles"] == ["guest"]
    assert claims["token_type"] == "access"


def test_login_with_wrong_password_fails(api_client):
    user = UserFactory()

    response = api_client.post(reverse("auth-token"), {"email": user.email, "password": "wrong"})

    assert response.status_code == 401
    assert response.json()["status"] == 401


def test_refresh_rotates_token_and_rejects_reuse(api_client):
    tokens = login(api_client, UserFactory().email)

    first = api_client.post(reverse("auth-token-refresh"), {"refresh": tokens["refresh"]})
    reuse = api_client.post(reverse("auth-token-refresh"), {"refresh": tokens["refresh"]})

    assert first.status_code == 200
    assert first.data["refresh"] != tokens["refresh"]
    assert reuse.status_code == 401


def test_logout_revokes_refresh_token(api_client):
    tokens = login(api_client, UserFactory().email)

    logout = api_client.post(reverse("auth-logout"), {"refresh": tokens["refresh"]})
    refresh = api_client.post(reverse("auth-token-refresh"), {"refresh": tokens["refresh"]})

    assert logout.status_code == 200
    assert refresh.status_code == 401


def test_me_requires_authentication(api_client):
    response = api_client.get(reverse("users-me"))

    assert response.status_code == 401
    assert response["Content-Type"] == "application/problem+json"


def test_me_updates_profile_but_not_email(client_for):
    user = UserFactory()
    client = client_for(user)

    response = client.patch(
        reverse("users-me"), {"first_name": "Maria", "email": "hijack@example.com"}
    )

    user.refresh_from_db()
    assert response.status_code == 200
    assert user.first_name == "Maria"
    assert user.email != "hijack@example.com"


def test_become_host_returns_tokens_with_host_role(client_for):
    user = UserFactory()
    client = client_for(user)

    response = client.post(reverse("users-me-host"))

    assert response.status_code == 200
    assert response.data["user"]["is_host"] is True
    claims = verify_with_jwks(client, response.data["access"])
    assert claims["roles"] == ["guest", "host"]
