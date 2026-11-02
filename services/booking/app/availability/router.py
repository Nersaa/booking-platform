from datetime import date, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.auth import HostDep
from app.availability import service
from app.availability.schemas import (
    BlockIn,
    BlockOut,
    CalendarOut,
    PricingIn,
    PricingOut,
    QuoteOut,
    SeasonalRateIn,
    SeasonalRateOut,
)
from app.db import SessionDep
from app.listings.models import Listing

DEFAULT_CALENDAR_DAYS = 90


async def _host_listing(listing_id: UUID, session: SessionDep, host: HostDep) -> Listing:
    return await service.get_host_listing(session, listing_id, host)


HostListingDep = Annotated[Listing, Depends(_host_listing)]

host_router = APIRouter(
    prefix="/api/v1/host/listings/{listing_id}", tags=["host: pricing and availability"]
)


@host_router.get("/pricing")
async def get_pricing(session: SessionDep, listing: HostListingDep) -> PricingOut:
    return PricingOut.model_validate(await service.get_pricing(session, listing))


@host_router.put("/pricing")
async def set_pricing(session: SessionDep, listing: HostListingDep, body: PricingIn) -> PricingOut:
    return PricingOut.model_validate(await service.set_pricing(session, listing, body))


@host_router.get("/seasonal-rates")
async def list_seasonal_rates(
    session: SessionDep, listing: HostListingDep
) -> list[SeasonalRateOut]:
    rates = await service.list_seasonal_rates(session, listing)
    return [SeasonalRateOut.from_model(rate) for rate in rates]


@host_router.post("/seasonal-rates", status_code=status.HTTP_201_CREATED)
async def add_seasonal_rate(
    session: SessionDep, listing: HostListingDep, body: SeasonalRateIn
) -> SeasonalRateOut:
    return SeasonalRateOut.from_model(await service.add_seasonal_rate(session, listing, body))


@host_router.delete("/seasonal-rates/{rate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_seasonal_rate(session: SessionDep, listing: HostListingDep, rate_id: UUID) -> None:
    await service.delete_seasonal_rate(session, listing, rate_id)


@host_router.get("/blocks")
async def list_blocks(session: SessionDep, listing: HostListingDep) -> list[BlockOut]:
    return [BlockOut.from_model(block) for block in await service.list_blocks(session, listing)]


@host_router.post("/blocks", status_code=status.HTTP_201_CREATED)
async def add_block(session: SessionDep, listing: HostListingDep, body: BlockIn) -> BlockOut:
    return BlockOut.from_model(await service.add_block(session, listing, body))


@host_router.delete("/blocks/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_block(session: SessionDep, listing: HostListingDep, block_id: UUID) -> None:
    await service.delete_block(session, listing, block_id)


public_router = APIRouter(prefix="/api/v1/listings/{listing_id}", tags=["availability"])


@public_router.get("/calendar")
async def get_calendar(
    session: SessionDep,
    listing_id: UUID,
    start_date: date | None = None,
    end_date: date | None = None,
) -> CalendarOut:
    """Nightly availability and prices. Defaults to the next 90 nights."""
    start = start_date or service.today()
    end = end_date or start + timedelta(days=DEFAULT_CALENDAR_DAYS)
    return await service.get_calendar(session, listing_id, start, end)


@public_router.get("/quote")
async def get_quote(
    session: SessionDep,
    listing_id: UUID,
    check_in: date,
    check_out: date,
    guests: Annotated[int, Query(ge=1, le=50)] = 1,
) -> QuoteOut:
    """Full price breakdown for a stay. The same calculation is used when booking."""
    return await service.get_quote(session, listing_id, check_in, check_out, guests)
