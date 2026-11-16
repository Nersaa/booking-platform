import json
import time
import uuid
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from httpx import AsyncClient, Response
from sqlalchemy import select

from app.db import Database
from app.listings.models import Listing
from app.outbox import OutboxEvent
from app.payments import webhooks
from tests.conftest import WEBHOOK_SECRET

Headers = Callable[..., dict[str, str]]


async def book(
    client: AsyncClient,
    headers: dict[str, str],
    listing: Listing,
    check_in: date,
    nights: int = 3,
    guests: int = 2,
) -> Response:
    return await client.post(
        "/api/v1/bookings",
        json={
            "listing_id": str(listing.id),
            "check_in": str(check_in),
            "check_out": str(check_in + timedelta(days=nights)),
            "guests": guests,
        },
        headers=headers,
    )


async def send_webhook(
    client: AsyncClient,
    event_type: str,
    reference: UUID | str,
    amount: int = 0,
    *,
    event_id: str | None = None,
    secret: str = WEBHOOK_SECRET,
    timestamp: int | None = None,
) -> Response:
    body = json.dumps(
        {
            "id": event_id or f"evt_{uuid.uuid4().hex}",
            "type": event_type,
            "data": {
                "id": f"obj_{uuid.uuid4().hex[:8]}",
                "reference": str(reference),
                "amount": amount,
            },
        }
    ).encode()
    signature = webhooks.sign(secret, body, timestamp or int(time.time()))
    return await client.post(
        "/api/v1/payments/webhook",
        content=body,
        headers={"Content-Type": "application/json", webhooks.SIGNATURE_HEADER: signature},
    )


async def outbox_events(db: Database) -> list[dict[str, Any]]:
    async with db.sessions() as session:
        rows = await session.scalars(select(OutboxEvent).order_by(OutboxEvent.created_at))
        return [row.payload for row in rows]
