from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.bookings.models import Booking
from app.db import Database
from app.jobs import BackgroundJobs
from app.listings.models import Listing
from app.outbox import OutboxEvent
from tests.helpers import Headers, book, outbox_events
from tests.test_payments import confirmed_booking


class Published:
    def __init__(self, fail: bool = False) -> None:
        self.messages: list[tuple[str, dict[str, Any], str]] = []
        self.fail = fail

    async def __call__(self, routing_key: str, body: dict[str, Any], message_id: str) -> None:
        if self.fail:
            raise ConnectionError("broker is down")
        self.messages.append((routing_key, body, message_id))


def jobs(db: Database, publish: Published | None = None) -> BackgroundJobs:
    return BackgroundJobs(db, publish or Published())


async def test_sweeper_expires_unpaid_holds(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date, db: Database
) -> None:
    await book(client, auth(uuid4()), priced_listing, next_monday)
    assert await jobs(db).expire_holds() == 0

    async with db.engine.begin() as connection:
        await connection.execute(text("UPDATE bookings SET hold_expires_at = now()"))

    assert await jobs(db).expire_holds() == 1
    async with db.sessions() as session:
        assert (await session.scalars(select(Booking.status))).all() == ["expired"]


async def test_finished_stays_are_completed_and_announced(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date, db: Database
) -> None:
    await confirmed_booking(client, priced_listing, auth, next_monday)
    async with db.engine.begin() as connection:
        await connection.execute(
            text("UPDATE bookings SET period = daterange(current_date - 3, current_date)")
        )

    assert await jobs(db).complete_stays() == 1
    assert [e["event_type"] for e in await outbox_events(db)][-1] == "booking.completed"


async def test_relay_publishes_outbox_events_once(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date, db: Database
) -> None:
    await confirmed_booking(client, priced_listing, auth, next_monday)
    publish = Published()

    assert await jobs(db, publish).relay_outbox() == 1
    assert await jobs(db, publish).relay_outbox() == 0

    [(routing_key, body, message_id)] = publish.messages
    assert routing_key == "booking.confirmed"
    assert body["event_id"] == message_id


async def test_relay_keeps_events_while_broker_is_down(
    client: AsyncClient, priced_listing: Listing, auth: Headers, next_monday: date, db: Database
) -> None:
    await confirmed_booking(client, priced_listing, auth, next_monday)

    with pytest.raises(ConnectionError):
        await jobs(db, Published(fail=True)).relay_outbox()

    async with db.sessions() as session:
        pending = await session.scalars(
            select(OutboxEvent).where(OutboxEvent.published_at.is_(None))
        )
        assert len(pending.all()) == 1


async def test_job_loop_survives_failures(db: Database) -> None:
    calls = 0

    async def flaky() -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        raise SystemExit  # stop the endless loop on the second run

    with pytest.raises(SystemExit):
        await BackgroundJobs._every(0, flaky, "flaky")
    assert calls == 2
