from typing import Any, cast

from contracts import ListingSnapshot
from sqlalchemy import CursorResult, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.listings.models import Listing


async def apply_listing_snapshot(session: AsyncSession, snapshot: ListingSnapshot) -> bool:
    """Upsert the read model if the snapshot is newer. Returns False for stale or duplicate ones.

    A single statement does the version check, so concurrent consumers cannot overwrite a
    newer snapshot with an older one.
    """
    values = snapshot.model_dump()
    values["amenities"] = list(snapshot.amenities)
    insert_stmt = insert(Listing).values(**values)
    stmt = insert_stmt.on_conflict_do_update(
        index_elements=[Listing.id],
        set_={
            **{name: insert_stmt.excluded[name] for name in values if name != "id"},
            "synced_at": func.now(),
        },
        where=Listing.version < insert_stmt.excluded.version,
    )
    result = cast(CursorResult[Any], await session.execute(stmt))
    return result.rowcount == 1
