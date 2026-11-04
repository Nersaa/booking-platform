"""Keyset (cursor) pagination.

A page ends with an opaque cursor holding the sort key of its last row; the next page
starts strictly after it. Unlike OFFSET, the database seeks straight to the position
through an index, so page 1000 costs the same as page 1, and rows inserted meanwhile
never shift a page or show up twice.
"""

import base64
import binascii
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, Select, tuple_
from sqlalchemy.orm import QueryableAttribute

from app.errors import DomainError

type CursorValue = int | float | Decimal | UUID | date | datetime

Limit = Annotated[int, Query(ge=1, le=100, description="Page size.")]
Cursor = Annotated[
    str | None, Query(max_length=500, description="`next_cursor` of the previous page.")
]


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = Field(description="Pass as `cursor` to get the next page.")


class InvalidCursorError(DomainError):
    code = "invalid_cursor"


@dataclass(frozen=True)
class Keyset:
    """An ordering whose last key is unique, so every row has exactly one position."""

    kind: str
    keys: Sequence[ColumnElement[Any] | QueryableAttribute[Any]]
    types: Sequence[type[CursorValue]]
    descending: bool = False

    def apply[S: Select[Any]](self, stmt: S, cursor: str | None, limit: int) -> S:
        """Orders, seeks past the cursor and fetches one extra row to know if more exist."""
        position = tuple_(*self.keys)
        if cursor:
            after = tuple_(*decode_cursor(cursor, self.kind, self.types))
            stmt = stmt.where(position < after if self.descending else position > after)
        order = [key.desc() if self.descending else key.asc() for key in self.keys]
        return stmt.order_by(*order).limit(limit + 1)

    def page[R](
        self, rows: Sequence[R], limit: int, key: Callable[[R], Sequence[CursorValue]]
    ) -> tuple[list[R], str | None]:
        items = list(rows[:limit])
        if len(rows) <= limit:
            return items, None
        return items, encode_cursor(self.kind, key(items[-1]))


def encode_cursor(kind: str, values: Sequence[CursorValue]) -> str:
    plain = [v if isinstance(v, int | float) else _text(v) for v in values]
    raw = json.dumps([kind, *plain], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str, kind: str, types: Sequence[type[CursorValue]]) -> list[Any]:
    """Reads a cursor made for the same kind of listing, or fails with 400."""
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        cursor_kind, *values = json.loads(raw)
        if cursor_kind != kind or len(values) != len(types):
            raise ValueError(cursor_kind)
        return [_parse(type_, value) for type_, value in zip(types, values, strict=True)]
    except (ValueError, TypeError, binascii.Error, InvalidOperation) as exc:
        raise InvalidCursorError("The cursor is invalid or belongs to another query.") from exc


def _text(value: CursorValue) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


def _parse(type_: type[CursorValue], value: Any) -> CursorValue:
    if type_ is float:
        if not isinstance(value, int | float):
            raise TypeError(value)
        return float(value)
    if type_ is int:
        if not isinstance(value, int):
            raise TypeError(value)
        return value
    if not isinstance(value, str):
        raise TypeError(value)
    if type_ is datetime:
        return datetime.fromisoformat(value)
    if type_ is date:
        return date.fromisoformat(value)
    if type_ is Decimal:
        return Decimal(value)
    return UUID(value)
