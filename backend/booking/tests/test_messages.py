from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.listings.models import Listing
from tests.helpers import Headers, book


@pytest.fixture
async def booking(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date
) -> dict[str, Any]:
    data: dict[str, Any] = (await book(client, auth(uuid4()), priced_listing, next_monday)).json()
    return data


async def test_guest_and_host_talk_about_a_booking(
    client: AsyncClient, booking: dict[str, Any], auth: Headers
) -> None:
    guest = auth(booking["guest_id"])
    host = auth(booking["host_id"], "host")
    guest_url = f"/api/v1/bookings/{booking['id']}/messages"
    host_url = f"/api/v1/host/bookings/{booking['id']}/messages"

    asked = await client.post(guest_url, json={"text": "When can we check in?"}, headers=guest)
    answered = await client.post(host_url, json={"text": "From 3 pm."}, headers=host)
    seen_by_guest = await client.get(guest_url, headers=guest)
    seen_by_host = await client.get(host_url, headers=host)

    assert asked.status_code == answered.status_code == 201
    assert asked.json()["from_host"] is False
    assert answered.json()["from_host"] is True
    expected = [("When can we check in?", False), ("From 3 pm.", True)]
    assert [(m["text"], m["from_host"]) for m in seen_by_guest.json()] == expected
    assert seen_by_host.json() == seen_by_guest.json()


async def test_strangers_cannot_read_or_write(
    client: AsyncClient, booking: dict[str, Any], auth: Headers
) -> None:
    url = f"/api/v1/bookings/{booking['id']}/messages"
    stranger = auth(uuid4())
    other_host = auth(uuid4(), "host")

    read = await client.get(url, headers=stranger)
    write = await client.post(url, json={"text": "Hi"}, headers=stranger)
    host_read = await client.get(
        f"/api/v1/host/bookings/{booking['id']}/messages", headers=other_host
    )

    assert read.status_code == write.status_code == host_read.status_code == 404


async def test_empty_messages_are_rejected(
    client: AsyncClient, booking: dict[str, Any], auth: Headers
) -> None:
    response = await client.post(
        f"/api/v1/bookings/{booking['id']}/messages",
        json={"text": ""},
        headers=auth(booking["guest_id"]),
    )

    assert response.status_code == 422
