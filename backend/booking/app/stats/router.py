from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.auth import HostDep
from app.db import SessionDep
from app.stats.schemas import HostStatsOut
from app.stats.service import host_stats

router = APIRouter(prefix="/api/v1/host/stats", tags=["host: stats"])


@router.get("")
async def get_host_stats(
    session: SessionDep,
    host: HostDep,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    currency: Annotated[str | None, Query(pattern="^[A-Z]{3}$")] = None,
) -> HostStatsOut:
    """Revenue, bookings, occupancy by month and the best places of one year.

    Without `currency` the money is counted in the host's most used one.
    """
    year = year or datetime.now(UTC).year
    return await host_stats(session, host, year, currency)
