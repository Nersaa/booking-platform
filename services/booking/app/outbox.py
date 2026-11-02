"""Transactional outbox, the same pattern as in Catalog (see docs/adr/0004).

Events are inserted in the transaction of the change; the worker relays them to RabbitMQ
with publisher confirms and `mandatory`, so unroutable events stay here until a consumer
queue exists.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import DateTime, String, delete, func, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

logger = logging.getLogger(__name__)

PUBLISHED_RETENTION = timedelta(days=7)

Publish = Callable[[str, dict[str, Any], str], Awaitable[None]]


class OutboxEvent(Base):
    __tablename__ = "outbox"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    routing_key: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class Event(Protocol):
    @property
    def event_id(self) -> UUID: ...

    @property
    def routing_key(self) -> str: ...

    def model_dump(self, *, mode: str) -> dict[str, Any]: ...


def outbox_add(session: AsyncSession, event: Event) -> None:
    if not session.in_transaction():
        raise RuntimeError("Outbox events must be written inside the transaction they describe.")
    session.add(
        OutboxEvent(
            id=event.event_id, routing_key=event.routing_key, payload=event.model_dump(mode="json")
        )
    )


async def relay_batch(
    sessions: async_sessionmaker[AsyncSession], publish: Publish, batch_size: int = 100
) -> int:
    """Publish pending events in order; returns how many went out. Raises if none could."""
    async with sessions.begin() as session:
        pending = (
            await session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.created_at)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()
        published: list[UUID] = []
        for event in pending:
            try:
                await publish(event.routing_key, event.payload, str(event.id))
            except Exception:
                if not published:
                    raise
                logger.warning("Relay stopped mid-batch", exc_info=True)
                break
            published.append(event.id)
        if published:
            await session.execute(
                update(OutboxEvent)
                .where(OutboxEvent.id.in_(published))
                .values(published_at=func.now())
            )
    return len(published)


async def purge_published(session: AsyncSession) -> int:
    result = await session.execute(
        delete(OutboxEvent)
        .where(OutboxEvent.published_at < func.now() - PUBLISHED_RETENTION)
        .returning(OutboxEvent.id)
    )
    return len(result.all())
