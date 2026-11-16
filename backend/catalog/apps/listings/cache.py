"""Cache of the public listing page, the most read response of the catalog.

Entries are dropped when the listing's transaction commits (see `emit_listing_event`);
the TTL only bounds the rare race of a reader refilling the cache with a pre-commit read.
"""

from functools import partial
from typing import Any
from uuid import UUID

from django.core.cache import cache
from django.db import transaction

PUBLIC_LISTING_TTL_SECONDS = 300


def _key(listing_id: UUID | str) -> str:
    return f"listings:public:v1:{listing_id}"


def get_public_listing(listing_id: UUID | str) -> dict[str, Any] | None:
    data: dict[str, Any] | None = cache.get(_key(listing_id))
    return data


def set_public_listing(listing_id: UUID | str, data: dict[str, Any]) -> None:
    cache.set(_key(listing_id), data, PUBLIC_LISTING_TTL_SECONDS)


def invalidate_public_listing(listing_id: UUID | str) -> None:
    transaction.on_commit(partial(cache.delete, _key(listing_id)))
