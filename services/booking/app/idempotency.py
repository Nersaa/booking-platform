"""Idempotency keys for unsafe requests (RFC draft "The Idempotency-Key HTTP Header Field").

The key is stored in the same transaction as the operation itself:
- a retry after success gets the stored response back, nothing is done twice;
- a concurrent duplicate blocks on the primary key until the first request finishes,
  then replays its response;
- if the first request failed, its transaction (and the key) is rolled back, so a retry
  simply runs again.
"""

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import DateTime, SmallInteger, String, delete, func, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.errors import DomainError

KEY_TTL = timedelta(hours=24)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int | None] = mapped_column(SmallInteger)
    response_body: Mapped[Any | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class IdempotencyKeyReusedError(DomainError):
    status_code = 422
    code = "idempotency_key_reused"


@dataclass(frozen=True, slots=True)
class StoredResponse:
    status_code: int
    body: Any


IdempotencyKeyHeader = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=255,
        description="Unique per operation, e.g. a UUID. Retries must reuse it.",
    ),
]


def _fingerprint(operation: str, payload: Any) -> str:
    raw = json.dumps([operation, payload], sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


async def begin(
    session: AsyncSession, *, user_id: UUID, key: str, operation: str, payload: Any
) -> StoredResponse | None:
    """Claim the key for this request, or return the response of the earlier one."""
    request_hash = _fingerprint(operation, payload)
    claimed = await session.scalar(
        insert(IdempotencyKey)
        .values(user_id=user_id, key=key, request_hash=request_hash)
        .on_conflict_do_nothing()
        .returning(IdempotencyKey.key)
    )
    if claimed is not None:
        return None

    existing = await session.scalar(
        select(IdempotencyKey).where(IdempotencyKey.user_id == user_id, IdempotencyKey.key == key)
    )
    if existing is None or existing.status_code is None:  # pragma: no cover - rolled back race
        raise IdempotencyKeyReusedError("The request with this key is still being processed.")
    if existing.request_hash != request_hash:
        raise IdempotencyKeyReusedError(
            "This Idempotency-Key was already used for a different request."
        )
    return StoredResponse(existing.status_code, existing.response_body)


async def complete(
    session: AsyncSession, *, user_id: UUID, key: str, status_code: int, body: Any
) -> None:
    existing = await session.get_one(IdempotencyKey, (user_id, key))
    existing.status_code = status_code
    existing.response_body = body


async def respond(
    session: AsyncSession,
    *,
    user_id: UUID,
    key: str,
    operation: str,
    payload: Any,
    status_code: int,
    action: Callable[[], Awaitable[BaseModel]],
) -> JSONResponse:
    """Run `action` once per key; later calls with the same key get the same response."""
    stored = await begin(session, user_id=user_id, key=key, operation=operation, payload=payload)
    if stored is not None:
        return JSONResponse(
            stored.body, status_code=stored.status_code, headers={"Idempotent-Replayed": "true"}
        )
    body = (await action()).model_dump(mode="json")
    await complete(session, user_id=user_id, key=key, status_code=status_code, body=body)
    return JSONResponse(body, status_code=status_code)


async def purge_expired(session: AsyncSession) -> int:
    result = await session.execute(
        delete(IdempotencyKey)
        .where(IdempotencyKey.created_at < func.now() - KEY_TTL)
        .returning(IdempotencyKey.key)
    )
    return len(result.all())
