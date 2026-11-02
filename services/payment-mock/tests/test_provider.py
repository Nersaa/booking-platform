import asyncio
import hashlib
import hmac
from typing import Any

import httpx
import pytest
from payment_mock.main import Provider, Settings, create_app, sign

API_KEY = "test-api-key"
AUTH = {"Authorization": f"Bearer {API_KEY}"}


@pytest.fixture
def sent() -> list[dict[str, Any]]:
    return []


@pytest.fixture
def provider(sent: list[dict[str, Any]]) -> Provider:
    async def capture(event: dict[str, Any]) -> None:
        sent.append(event)

    settings = Settings(
        api_key=API_KEY, webhook_secret="whsec", webhook_url="http://merchant/webhook"
    )
    return Provider(settings, send_webhook=capture)


@pytest.fixture
async def client(provider: Provider):
    transport = httpx.ASGITransport(app=create_app(provider))
    async with httpx.AsyncClient(transport=transport, base_url="http://mock") as client:
        yield client


async def create_payment(client: httpx.AsyncClient, key: str = "k1") -> dict[str, Any]:
    response = await client.post(
        "/v1/payments",
        json={"amount": 12_000, "currency": "EUR", "reference": "booking-payment-1"},
        headers={**AUTH, "Idempotency-Key": key},
    )
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


async def test_api_requires_the_merchant_key(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/v1/payments",
        json={"amount": 1, "currency": "EUR", "reference": "r"},
        headers={"Authorization": "Bearer wrong", "Idempotency-Key": "k"},
    )
    assert response.status_code == 401


async def test_same_idempotency_key_returns_the_same_payment(client: httpx.AsyncClient) -> None:
    first = await create_payment(client, key="same")
    second = await create_payment(client, key="same")
    other = await create_payment(client, key="other")

    assert first == second
    assert other["id"] != first["id"]
    assert first["checkout_url"].endswith(f"/checkout/{first['id']}")


async def test_paying_sends_a_webhook(
    client: httpx.AsyncClient, sent: list[dict[str, Any]]
) -> None:
    payment = await create_payment(client)

    page = await client.get(f"/checkout/{payment['id']}")
    paid = await client.post(f"/checkout/{payment['id']}/pay")
    await asyncio.sleep(0)

    assert "120.00 EUR" in page.text
    assert "succeeded" in paid.text
    [event] = sent
    assert event["type"] == "payment.succeeded"
    assert event["data"]["reference"] == "booking-payment-1"


async def test_declined_card_fails_the_payment_once(
    client: httpx.AsyncClient, sent: list[dict[str, Any]]
) -> None:
    payment = await create_payment(client)

    await client.post(f"/checkout/{payment['id']}/decline")
    await client.post(f"/checkout/{payment['id']}/pay")  # too late, already failed
    await asyncio.sleep(0)

    assert [e["type"] for e in sent] == ["payment.failed"]


async def test_refunds_are_limited_to_the_paid_amount(
    client: httpx.AsyncClient, sent: list[dict[str, Any]]
) -> None:
    payment = await create_payment(client)
    url = f"/v1/payments/{payment['id']}/refunds"

    early = await client.post(
        url, json={"amount": 100, "reference": "r0"}, headers={**AUTH, "Idempotency-Key": "r0"}
    )
    await client.post(f"/checkout/{payment['id']}/pay")
    half = await client.post(
        url, json={"amount": 6_000, "reference": "r1"}, headers={**AUTH, "Idempotency-Key": "r1"}
    )
    replay = await client.post(
        url, json={"amount": 6_000, "reference": "r1"}, headers={**AUTH, "Idempotency-Key": "r1"}
    )
    too_much = await client.post(
        url, json={"amount": 6_001, "reference": "r2"}, headers={**AUTH, "Idempotency-Key": "r2"}
    )
    await asyncio.sleep(0)

    assert early.status_code == 409
    assert half.status_code == 201
    assert replay.json() == half.json()
    assert too_much.status_code == 409
    assert [e["type"] for e in sent] == ["payment.succeeded", "refund.succeeded"]


def test_signature_is_hmac_of_timestamp_and_body() -> None:
    header = sign("secret", b'{"a":1}', 1_700_000_000)

    expected = hmac.new(b"secret", b'1700000000.{"a":1}', hashlib.sha256).hexdigest()
    assert header == f"t=1700000000,v1={expected}"
