import time
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.db import Database
from app.listings.models import Listing
from tests.factories import FakePaymentProvider
from tests.helpers import Headers, book, outbox_events, send_webhook


@pytest.fixture
async def booking(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> dict[str, Any]:
    response = await book(client, auth(uuid4()), priced_listing, next_monday)
    assert response.status_code == 201
    data: dict[str, Any] = response.json()
    return data


async def pay(client: AsyncClient, auth: Headers, booking: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/bookings/{booking['id']}/payments",
        headers=auth(booking["guest_id"]),
    )
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    return data


async def fetch(client: AsyncClient, auth: Headers, booking: dict[str, Any]) -> dict[str, Any]:
    response = await client.get(
        f"/api/v1/bookings/{booking['id']}", headers=auth(booking["guest_id"])
    )
    data: dict[str, Any] = response.json()
    return data


async def test_successful_payment_confirms_the_booking(
    client: AsyncClient, auth: Headers, booking: dict[str, Any], db: Database
) -> None:
    payment = await pay(client, auth, booking)
    assert payment["checkout_url"].startswith("http://pay/")
    assert payment["amount"] == booking["total"]

    webhook = await send_webhook(client, "payment.succeeded", payment["id"], payment["amount"])

    assert webhook.status_code == 204
    confirmed = await fetch(client, auth, booking)
    assert confirmed["status"] == "confirmed"
    assert confirmed["hold_expires_at"] is None
    [event] = await outbox_events(db)
    assert event["event_type"] == "booking.confirmed"
    assert event["booking"]["guest_id"] == booking["guest_id"]


async def test_asking_to_pay_twice_reuses_the_open_checkout(
    client: AsyncClient,
    auth: Headers,
    booking: dict[str, Any],
    payment_provider: FakePaymentProvider,
) -> None:
    first = await pay(client, auth, booking)
    second = await pay(client, auth, booking)

    assert second["id"] == first["id"]
    assert len(payment_provider.payments) == 1


async def test_duplicate_webhook_is_processed_once(
    client: AsyncClient, auth: Headers, booking: dict[str, Any], db: Database
) -> None:
    payment = await pay(client, auth, booking)

    for _ in range(3):
        response = await send_webhook(
            client, "payment.succeeded", payment["id"], event_id="evt_same"
        )
        assert response.status_code == 204

    assert len(await outbox_events(db)) == 1


@pytest.mark.parametrize(
    ("secret", "age_seconds"),
    [("wrong-secret", 0), (None, 3600)],
    ids=["bad signature", "replayed old request"],
)
async def test_unauthentic_webhooks_are_rejected(
    client: AsyncClient,
    auth: Headers,
    booking: dict[str, Any],
    secret: str | None,
    age_seconds: int,
) -> None:
    payment = await pay(client, auth, booking)
    kwargs: dict[str, Any] = {"timestamp": int(time.time()) - age_seconds}
    if secret:
        kwargs["secret"] = secret

    response = await send_webhook(client, "payment.succeeded", payment["id"], **kwargs)

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_signature"
    assert (await fetch(client, auth, booking))["status"] == "pending_payment"


async def test_declined_payment_can_be_retried(
    client: AsyncClient, auth: Headers, booking: dict[str, Any]
) -> None:
    declined = await pay(client, auth, booking)
    await send_webhook(client, "payment.failed", declined["id"])

    retry = await pay(client, auth, booking)

    assert retry["id"] != declined["id"]
    assert (await fetch(client, auth, booking))["status"] == "pending_payment"


async def test_provider_outage_is_reported_as_unavailable(
    client: AsyncClient,
    auth: Headers,
    booking: dict[str, Any],
    payment_provider: FakePaymentProvider,
) -> None:
    payment_provider.down = True

    response = await client.post(
        f"/api/v1/bookings/{booking['id']}/payments",
        headers=auth(booking["guest_id"]),
    )

    assert response.status_code == 503


async def test_payment_after_cancellation_is_refunded(
    client: AsyncClient, auth: Headers, booking: dict[str, Any]
) -> None:
    payment = await pay(client, auth, booking)
    cancel = await client.post(
        f"/api/v1/bookings/{booking['id']}/cancel",
        json={},
        headers=auth(booking["guest_id"]),
    )
    assert cancel.json()["refund_amount"] == 0

    await send_webhook(client, "payment.succeeded", payment["id"], payment["amount"])

    cancelled = await fetch(client, auth, booking)
    assert cancelled["status"] == "cancelled"
    assert cancelled["refund_amount"] == booking["total"]


async def confirmed_booking(
    client: AsyncClient, priced_listing: Listing, auth: Headers, check_in: date
) -> dict[str, Any]:
    booking: dict[str, Any] = (await book(client, auth(uuid4()), priced_listing, check_in)).json()
    payment = await pay(client, auth, booking)
    await send_webhook(client, "payment.succeeded", payment["id"], payment["amount"])
    return booking


@pytest.mark.parametrize(("days_ahead", "refund_share"), [(10, 1.0), (3, 0.5)])
async def test_guest_cancellation_refunds_by_policy(
    client: AsyncClient,
    priced_listing: Listing,
    auth: Headers,
    db: Database,
    payment_provider: FakePaymentProvider,
    days_ahead: int,
    refund_share: float,
) -> None:
    from app.availability.service import today

    booking = await confirmed_booking(
        client, priced_listing, auth, today() + timedelta(days=days_ahead)
    )

    response = await client.post(
        f"/api/v1/bookings/{booking['id']}/cancel",
        json={"reason": "Plans changed"},
        headers=auth(booking["guest_id"]),
    )

    assert response.status_code == 200, response.text
    cancelled = response.json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["cancelled_by"] == "guest"
    assert cancelled["refund_amount"] == int(booking["total"] * refund_share)

    [refund] = payment_provider.refunds.values()
    assert refund["amount"] == cancelled["refund_amount"]

    events = [e["event_type"] for e in await outbox_events(db)]
    assert events == ["booking.confirmed", "booking.cancelled"]


async def test_host_cancellation_refunds_in_full(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> None:
    booking = await confirmed_booking(client, priced_listing, auth, next_monday)

    response = await client.post(
        f"/api/v1/host/bookings/{booking['id']}/cancel",
        json={"reason": "Water leak"},
        headers=auth(priced_listing.host_id, "host"),
    )

    assert response.json()["refund_amount"] == booking["total"]
    assert response.json()["cancelled_by"] == "host"


async def test_cancellation_waits_for_the_provider_to_refund(
    client: AsyncClient,
    priced_listing: Listing,
    auth: Headers,
    next_monday: date,
    payment_provider: FakePaymentProvider,
) -> None:
    booking = await confirmed_booking(client, priced_listing, auth, next_monday)
    url = f"/api/v1/bookings/{booking['id']}/cancel"

    payment_provider.down = True
    failed = await client.post(url, json={}, headers=auth(booking["guest_id"]))
    payment_provider.down = False
    retried = await client.post(url, json={}, headers=auth(booking["guest_id"]))

    assert failed.status_code == 503
    assert retried.status_code == 200
    assert retried.json()["refund_amount"] == booking["total"]
    assert len(payment_provider.refunds) == 1


async def test_cancelled_booking_cannot_be_cancelled_again(
    client: AsyncClient, auth: Headers, booking: dict[str, Any]
) -> None:
    for expected in (200, 409):
        response = await client.post(
            f"/api/v1/bookings/{booking['id']}/cancel",
            json={},
            headers=auth(booking["guest_id"]),
        )
        assert response.status_code == expected
