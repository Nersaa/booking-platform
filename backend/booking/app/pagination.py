"""Limit/offset pagination for list endpoints."""

from typing import Annotated, Any

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

Limit = Annotated[int, Query(ge=1, le=100, description="Page size.")]
Offset = Annotated[int, Query(ge=0, description="How many items to skip.")]


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


async def count(session: AsyncSession, stmt: Select[Any]) -> int:
    """Number of rows the query returns without paging."""
    total = await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    return total or 0
